#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import ssl
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


REQUIRED_CAPABILITIES = {
    "semantic_events",
    "controlled_timeouts",
    "failure_evidence_bundle",
    "network_text_bodies",
    "network_redaction",
    "request_forward_provenance",
    "case_console_page_errors",
    "table_assertion_snapshot",
    "business_assertion_receipts",
    "verification_entrypoint",
    "atomic_evidence_writes",
}


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_verification_manifest(
    path: Path,
    *,
    dsl: Path,
    readiness_file: Path,
    cleanup_dsl: Path | None = None,
) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        raise ValueError(f"verification manifest not found: {path}")
    content = path.read_bytes()
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"verification manifest is not valid JSON: {path}") from exc
    required = {"inputs", "baseline", "fingerprints"}
    missing = sorted(required - set(payload)) if isinstance(payload, dict) else sorted(required)
    if missing:
        raise ValueError(f"verification manifest missing: {', '.join(missing)}")
    baseline_required = {"business_repo_head", "business_repo_porcelain", "file_sha256"}
    baseline_missing = sorted(baseline_required - set(payload["baseline"]))
    if baseline_missing:
        raise ValueError(f"verification manifest baseline missing: {', '.join(baseline_missing)}")
    fingerprint_required = {
        "release_package_sha256",
        "ydf_browser",
        "agents_skill",
        "helper_sha256",
    }
    fingerprint_missing = sorted(fingerprint_required - set(payload["fingerprints"]))
    if fingerprint_missing:
        raise ValueError(f"verification manifest fingerprints missing: {', '.join(fingerprint_missing)}")
    for key, expected in (("dsl", dsl), ("readiness", readiness_file)):
        actual = payload["inputs"].get(key)
        if not actual or Path(str(actual)).expanduser().resolve() != expected.resolve():
            raise ValueError(f"verification manifest inputs.{key} does not match the run")
    if cleanup_dsl is not None:
        actual = payload["inputs"].get("cleanup_dsl")
        if not actual or Path(str(actual)).expanduser().resolve() != cleanup_dsl.resolve():
            raise ValueError("verification manifest inputs.cleanup_dsl does not match the run")
    return payload, hashlib.sha256(content).hexdigest()


def validate_readiness_items(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list) or not items:
        raise ValueError("readiness must be a non-empty list")
    output = []
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise ValueError(f"readiness[{index}] must be an object")
        required = {"target", "mode", "url", "timeout_seconds", "tls_verify"}
        missing = sorted(required - set(raw))
        if missing:
            raise ValueError(f"readiness[{index}] missing: {', '.join(missing)}")
        mode = str(raw["mode"])
        if mode not in {"http_reachable", "semantic_probe"}:
            raise ValueError(f"readiness[{index}].mode is unsupported: {mode}")
        if not str(raw["target"]).strip() or not str(raw["url"]).strip():
            raise ValueError(f"readiness[{index}] target and url must be non-empty")
        if int(raw["timeout_seconds"]) <= 0:
            raise ValueError(f"readiness[{index}].timeout_seconds must be positive")
        if not isinstance(raw["tls_verify"], bool):
            raise ValueError(f"readiness[{index}].tls_verify must be boolean")
        if mode == "semantic_probe":
            semantic_required = {"expected_status", "json_path", "equals"}
            semantic_missing = sorted(semantic_required - set(raw))
            if semantic_missing:
                raise ValueError(f"readiness[{index}] missing: {', '.join(semantic_missing)}")
        output.append(dict(raw))
    return output


def _json_path(value: Any, path: str) -> Any:
    if not path.startswith("$."):
        raise ValueError(f"json_path only supports $.field paths: {path}")
    current = value
    for part in path[2:].split("."):
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"json_path not found: {path}")
        current = current[part]
    return current


def check_readiness(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for item in validate_readiness_items(items):
        context = None if item["tls_verify"] else ssl._create_unverified_context()
        status = 0
        body = b""
        try:
            with urlopen(
                Request(str(item["url"]), method="GET"),
                timeout=float(item["timeout_seconds"]),
                context=context,
            ) as response:
                status = int(response.status)
                body = response.read()
        except HTTPError as exc:
            status = int(exc.code)
            body = exc.read()
        except Exception as exc:
            raise RuntimeError(f"blocked/environment_unavailable: {item['target']}: {exc}") from exc
        if item["mode"] == "semantic_probe":
            if status != int(item["expected_status"]):
                raise RuntimeError(
                    f"blocked/environment_unavailable: {item['target']}: status={status}"
                )
            actual = _json_path(json.loads(body.decode("utf-8")), str(item["json_path"]))
            if actual != item["equals"]:
                raise RuntimeError(
                    f"blocked/environment_unavailable: {item['target']}: semantic value mismatch"
                )
        results.append({"target": item["target"], "ready": True, "status": status})
    return results


def installed_cli() -> tuple[str, str]:
    executable = shutil.which("ydf-browser")
    if not executable:
        raise ValueError("installed ydf-browser not found in PATH")
    path = Path(executable).expanduser().absolute()
    return str(path), str(path.resolve())


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_frozen_fingerprints(expected: dict[str, Any], actual: dict[str, str]) -> dict[str, Any]:
    keys = {"ydf_browser", "agents_skill", "helper_sha256"}
    mismatches = sorted(key for key in keys if str(expected.get(key) or "") != actual.get(key))
    if mismatches:
        raise RuntimeError(
            "blocked/contract_incompatible: frozen fingerprint mismatch: " + ", ".join(mismatches)
        )
    return {"verified": True, "actual": actual}


def verify_frozen_fingerprints(manifest: dict[str, Any], executable_realpath: str) -> dict[str, Any]:
    agents_root = (
        Path(os.environ.get("AGENTS_HOME", "~/.agents")).expanduser()
        / "skills"
        / "gov-ydfdev-browser"
    )
    helper = Path(__file__).resolve()
    if not agents_root.is_dir():
        raise RuntimeError("blocked/contract_incompatible: default-installed skill missing: agents_skill")
    if helper != (agents_root / "scripts" / "ai_verification.py").resolve():
        raise RuntimeError("blocked/contract_incompatible: helper is not from a default-installed skill")
    actual = {
        "ydf_browser": _sha256_file(Path(executable_realpath)),
        "agents_skill": directory_fingerprint(agents_root),
        "helper_sha256": _sha256_file(helper),
    }
    return validate_frozen_fingerprints(manifest["fingerprints"], actual)


def doctor_preflight(executable: str) -> dict[str, Any]:
    environment = {**os.environ, "YDF_BROWSER_AUTO_UPDATE": "0"}
    completed = subprocess.run(
        [executable, "doctor", "--skip-config"],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"blocked/contract_incompatible: doctor failed: {completed.stderr.strip()}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("blocked/contract_incompatible: doctor did not return JSON") from exc
    contract_version = str(payload.get("contract_version") or "")
    available = set((payload.get("capabilities") or {}).get("available") or [])
    missing = sorted(REQUIRED_CAPABILITIES - available)
    if contract_version.split(".", 1)[0] != "1" or missing:
        raise RuntimeError(
            f"blocked/contract_incompatible: contract={contract_version}; missing={missing}"
        )
    skill_check = ((payload.get("checks") or {}).get("skill_compatibility") or {})
    if skill_check.get("status") == "incompatible":
        raise RuntimeError("blocked/contract_incompatible: installed skill is incompatible with runtime")
    return payload


def run_cli_process(
    command: list[str],
    *,
    timeout_seconds: int,
    environment: dict[str, str],
) -> dict[str, Any]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    externally_terminated = False
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds + 30)
    except subprocess.TimeoutExpired:
        externally_terminated = True
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
    return {
        "returncode": process.returncode,
        "outcome": "terminated" if externally_terminated else "completed",
        "reason_code": "external_termination" if externally_terminated else None,
        **({"stderr": stderr[-4000:]} if stderr else {}),
        **({"stdout": stdout[-4000:]} if stdout else {}),
    }


def _observed_run_command(
    *,
    executable: str,
    dsl: Path,
    report_file: Path,
    step_timeout_seconds: int,
    case_timeout_seconds: int,
    run_timeout_seconds: int,
    forward_strip_prefix: list[str],
    variable_overrides: list[str],
) -> list[str]:
    command = [
        executable,
        "run",
        "--dsl",
        str(dsl),
        "--headless",
        "--ai-observe",
        "--report-file",
        str(report_file),
        "--step-timeout-seconds",
        str(step_timeout_seconds),
        "--case-timeout-seconds",
        str(case_timeout_seconds),
        "--run-timeout-seconds",
        str(run_timeout_seconds),
    ]
    for rule in forward_strip_prefix:
        command.extend(["--forward-strip-prefix", rule])
    for override in variable_overrides:
        command.extend(["--var", override])
    return command


def run_cleanup(
    *,
    executable: str,
    cleanup_dsl: Path,
    cleanup_root: Path,
    step_timeout_seconds: int,
    case_timeout_seconds: int,
    run_timeout_seconds: int,
    forward_strip_prefix: list[str],
    variable_overrides: list[str],
    environment: dict[str, str],
) -> dict[str, Any]:
    attempts = []
    for attempt in (1, 2):
        report_file = cleanup_root / f"attempt-{attempt}" / "report.json"
        execution = run_cli_process(
            _observed_run_command(
                executable=executable,
                dsl=cleanup_dsl,
                report_file=report_file,
                step_timeout_seconds=step_timeout_seconds,
                case_timeout_seconds=case_timeout_seconds,
                run_timeout_seconds=run_timeout_seconds,
                forward_strip_prefix=forward_strip_prefix,
                variable_overrides=variable_overrides,
            ),
            timeout_seconds=run_timeout_seconds,
            environment=environment,
        )
        try:
            report_success = bool(json.loads(report_file.read_text(encoding="utf-8")).get("success"))
        except (FileNotFoundError, OSError, ValueError):
            report_success = False
        attempts.append(
            {
                "attempt": attempt,
                "report": report_file.relative_to(cleanup_root.parent).as_posix(),
                **execution,
            }
        )
        if execution["outcome"] == "completed" and execution["returncode"] == 0 and report_success:
            return {"success": True, "attempts": attempts}
    return {"success": False, "reason_code": "cleanup_failed", "attempts": attempts}


def run_observed(
    *,
    dsl: Path,
    run_dir: Path,
    readiness_file: Path,
    verification_manifest: Path,
    step_timeout_seconds: int,
    case_timeout_seconds: int,
    run_timeout_seconds: int,
    forward_strip_prefix: list[str],
    cleanup_dsl: Path | None = None,
    variable_overrides: list[str] | None = None,
) -> dict[str, Any]:
    manifest, manifest_sha256 = load_verification_manifest(
        verification_manifest,
        dsl=dsl,
        readiness_file=readiness_file,
        cleanup_dsl=cleanup_dsl,
    )
    executable_path, executable_realpath = installed_cli()
    fingerprints = verify_frozen_fingerprints(manifest, executable_realpath)
    doctor = doctor_preflight(executable_path)
    readiness = check_readiness(json.loads(readiness_file.read_text(encoding="utf-8"))["readiness"])
    dsl_sha256 = hashlib.sha256(dsl.read_bytes()).hexdigest()
    run_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(run_dir, 0o700)
    overrides = list(variable_overrides or [])
    helper_sha256 = str(fingerprints["actual"]["helper_sha256"])
    environment = {
        **os.environ,
        "YDF_BROWSER_AUTO_UPDATE": "0",
        "YDF_BROWSER_AI_HELPER_SHA256": helper_sha256,
    }
    execution = run_cli_process(
        _observed_run_command(
            executable=executable_path,
            dsl=dsl,
            report_file=run_dir / "report.json",
            step_timeout_seconds=step_timeout_seconds,
            case_timeout_seconds=case_timeout_seconds,
            run_timeout_seconds=run_timeout_seconds,
            forward_strip_prefix=forward_strip_prefix,
            variable_overrides=overrides,
        ),
        timeout_seconds=run_timeout_seconds,
        environment=environment,
    )
    cleanup = (
        run_cleanup(
            executable=executable_path,
            cleanup_dsl=cleanup_dsl,
            cleanup_root=run_dir / "cleanup",
            step_timeout_seconds=step_timeout_seconds,
            case_timeout_seconds=case_timeout_seconds,
            run_timeout_seconds=run_timeout_seconds,
            forward_strip_prefix=forward_strip_prefix,
            variable_overrides=overrides,
            environment=environment,
        )
        if cleanup_dsl is not None
        else {"success": False, "reason_code": "cleanup_not_configured", "attempts": []}
    )
    result = {
        **execution,
        "report": "report.json" if (run_dir / "report.json").is_file() else None,
        "events": "events.jsonl" if (run_dir / "events.jsonl").is_file() else None,
        "doctor": {
            "executable_path": executable_path,
            "executable_realpath": executable_realpath,
            "tool_version": doctor.get("tool_version"),
            "contract_version": doctor.get("contract_version"),
            "capabilities": doctor.get("capabilities"),
        },
        "readiness": readiness,
        "verification_manifest": {
            "path": str(verification_manifest),
            "sha256": manifest_sha256,
        },
        "dsl": {"path": str(dsl.resolve()), "sha256": dsl_sha256},
        "variables": {"override_keys": sorted({item.split("=", 1)[0] for item in overrides})},
        "verification": {
            "entrypoint": "skill_helper",
            "verification_eligible": True,
            "helper_sha256": helper_sha256,
        },
        "fingerprints": fingerprints,
        "cleanup": cleanup,
    }
    atomic_write_json(run_dir / "external-result.json", result)
    return result


def _walk_receipts(value: Any) -> list[dict[str, Any]]:
    receipts = []
    if isinstance(value, dict):
        receipt = value.get("assertion_receipt")
        if isinstance(receipt, dict):
            receipts.append(receipt)
        for nested in value.values():
            receipts.extend(_walk_receipts(nested))
    elif isinstance(value, list):
        for nested in value:
            receipts.extend(_walk_receipts(nested))
    return receipts


def filter_relevant_requests(run_dir: Path, business_id: str) -> dict[str, Any]:
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    receipts = _walk_receipts(report)
    candidate_ids = {
        str(request_id)
        for receipt in receipts
        for request_id in receipt.get("candidate_request_ids") or []
    }
    ui_identity_matched = business_id in json.dumps(receipts, ensure_ascii=False)
    records_by_id: dict[str, list[dict[str, Any]]] = {}
    index = run_dir / "artifacts" / "network" / "index.jsonl"
    for line in index.read_text(encoding="utf-8").splitlines() if index.is_file() else []:
        record = json.loads(line)
        request_id = str(record.get("request_id") or "")
        if request_id in candidate_ids:
            records_by_id.setdefault(request_id, []).append(record)
    requests = []
    for request_id, records in records_by_id.items():
        api_identity_matched = False
        for record in records:
            for key in ("request_body", "response_body"):
                reference = record.get(key)
                path = reference.get("path") if isinstance(reference, dict) else None
                if path and business_id in (run_dir / path).read_text(encoding="utf-8"):
                    api_identity_matched = True
        completed = next((item for item in reversed(records) if item.get("event") == "request_completed"), {})
        forwarding = completed.get("forwarding") if isinstance(completed.get("forwarding"), dict) else {}
        requests.append(
            {
                "request_id": request_id,
                "api_identity_matched": api_identity_matched,
                "ui_identity_matched": ui_identity_matched,
                "local_forward_hit": bool(forwarding.get("matched") and forwarding.get("success")),
                "actual_url": completed.get("actual_url"),
                "status": completed.get("status"),
            }
        )
    return {"business_id": business_id, "ui_identity_matched": ui_identity_matched, "requests": requests}


def validate_verification_result(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("status") not in {"verified", "not_verified", "invalid"}:
        raise ValueError("status must be verified, not_verified, or invalid")
    required = {"status", "reason_code", "runs", "cleanup", "fingerprints"}
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"verification result missing: {', '.join(missing)}")
    if payload["status"] == "verified":
        red = [run for run in payload["runs"] if run.get("phase") == "red" and run.get("qualified")]
        green = [run for run in payload["runs"] if run.get("phase") == "green" and run.get("qualified")]
        if len(red) != 1:
            raise ValueError("verified requires exactly one qualified red run")
        if len(green) != 2:
            raise ValueError("verified requires exactly two qualified green runs")
        dsl_hashes = {str(run.get("dsl_sha256") or "") for run in [*red, *green]}
        if "" in dsl_hashes or len(dsl_hashes) != 1:
            raise ValueError("verified requires the same DSL content for qualified red and green runs")
        qualified = [*red, *green]
        business_ids = [str(run.get("api_business_id") or "") for run in qualified]
        if any(
            not business_id or business_id != str(run.get("ui_business_id") or "")
            for business_id, run in zip(business_ids, qualified)
        ):
            raise ValueError("verified requires matching non-empty API and UI business identifiers")
        if len(set(business_ids)) != len(business_ids):
            raise ValueError("verified requires fresh business identifiers for red and green runs")
        run_dirs = [str(run.get("run_dir") or "") for run in qualified]
        if "" in run_dirs or len(set(run_dirs)) != len(run_dirs):
            raise ValueError("verified requires distinct run directories")
        for run, business_id in zip(qualified, business_ids):
            _validate_qualified_run_evidence(run, business_id)
        cleanup_ids = {str(item) for item in payload["cleanup"].get("identifiers") or []}
        if not set(business_ids) <= cleanup_ids:
            raise ValueError("verified cleanup must cover every qualified business identifier")
        if not payload["cleanup"].get("success"):
            raise ValueError("verified requires successful cleanup")
        if not payload["fingerprints"].get("verified"):
            raise ValueError("verified requires matching fingerprints")
    return payload


def _validate_qualified_run_evidence(run: dict[str, Any], business_id: str) -> None:
    phase = str(run.get("phase") or "")
    expected_outcome = "assertion_failed" if phase == "red" else "passed"
    if run.get("tool_outcome") != expected_outcome:
        raise ValueError(f"qualified {phase} run requires tool_outcome={expected_outcome}")
    if not run.get("local_forward_hit"):
        raise ValueError("qualified run requires a local forward hit")
    receipt = run.get("assertion_receipt")
    if not isinstance(receipt, dict) or business_id not in json.dumps(receipt, ensure_ascii=False):
        raise ValueError("qualified run assertion receipt must contain its business identifier")

    run_dir = Path(str(run.get("run_dir") or "")).expanduser()
    if not run_dir.is_absolute() or not run_dir.is_dir():
        raise ValueError("qualified run_dir must be an existing absolute directory")
    external_path = run_dir / "external-result.json"
    report_path = run_dir / "report.json"
    index_path = run_dir / "artifacts" / "network" / "index.jsonl"
    if not external_path.is_file() or not report_path.is_file() or not index_path.is_file():
        raise ValueError("qualified run requires helper, report, and network evidence in one run directory")
    external = json.loads(external_path.read_text(encoding="utf-8"))
    if (external.get("dsl") or {}).get("sha256") != run.get("dsl_sha256"):
        raise ValueError("qualified run DSL hash must match its helper evidence")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    external_verification = external.get("verification") or {}
    report_verification = (report.get("run") or {}).get("verification") or {}
    helper_sha256 = str(external_verification.get("helper_sha256") or "")
    if not (
        external_verification.get("entrypoint") == "skill_helper"
        and external_verification.get("verification_eligible") is True
        and report_verification.get("entrypoint") == "skill_helper"
        and report_verification.get("verification_eligible") is True
        and helper_sha256
        and helper_sha256 == str(report_verification.get("helper_sha256") or "")
    ):
        raise ValueError("qualified run must come from the frozen skill helper")
    if not (external.get("fingerprints") or {}).get("verified"):
        raise ValueError("qualified run requires verified frozen fingerprints")
    actual_helper_sha256 = str(
        ((external.get("fingerprints") or {}).get("actual") or {}).get("helper_sha256") or ""
    )
    if helper_sha256 != actual_helper_sha256:
        raise ValueError("qualified run helper fingerprint must match its entrypoint")
    if not (external.get("cleanup") or {}).get("success"):
        raise ValueError("qualified run requires successful helper cleanup")
    report_receipts = _walk_receipts(report)
    if receipt not in report_receipts:
        raise ValueError("qualified run assertion receipt must come from its report")

    flow = run.get("flow_request_ids")
    required_flow = {"precondition", "mutation", "postcondition"}
    if not isinstance(flow, dict) or not required_flow <= set(flow):
        raise ValueError("qualified run requires precondition, mutation, and postcondition request IDs")
    request_ids = {key: str(flow.get(key) or "") for key in required_flow}
    if "" in request_ids.values() or len(set(request_ids.values())) != len(request_ids):
        raise ValueError("qualified run flow request IDs must be non-empty and distinct")
    if str(run.get("request_id") or "") != request_ids["postcondition"]:
        raise ValueError("qualified run selected request must be its postcondition request")

    completed = {}
    for line in index_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        request_id = str(record.get("request_id") or "")
        if request_id in request_ids.values() and record.get("event") == "request_completed":
            completed[request_id] = record
    if set(completed) != set(request_ids.values()):
        raise ValueError("qualified run flow requests must complete in the same run directory")
    if not (
        int(completed[request_ids["precondition"]].get("sequence") or 0)
        < int(completed[request_ids["mutation"]].get("sequence") or 0)
        < int(completed[request_ids["postcondition"]].get("sequence") or 0)
    ):
        raise ValueError("qualified run flow requests must preserve precondition, mutation, postcondition order")
    receipt_candidates = {str(item) for item in receipt.get("candidate_request_ids") or []}
    for stage, request_id in request_ids.items():
        record = completed[request_id]
        forwarding = record.get("forwarding") or {}
        if not forwarding.get("matched") or not forwarding.get("success"):
            raise ValueError("qualified run flow requests must hit the intended local forward")
        if not _record_body_contains(run_dir, record, business_id):
            if phase == "red" and stage == "postcondition" and request_id in receipt_candidates:
                continue
            raise ValueError("qualified run flow requests must carry the same business identifier")


def _record_body_contains(run_dir: Path, record: dict[str, Any], business_id: str) -> bool:
    for key in ("request_body", "response_body"):
        reference = record.get(key)
        relative = reference.get("path") if isinstance(reference, dict) else None
        if not relative:
            continue
        path = (run_dir / str(relative)).resolve()
        if path.is_relative_to(run_dir.resolve()) and path.is_file():
            if business_id in path.read_text(encoding="utf-8"):
                return True
    return False


def directory_fingerprint(root: Path) -> str:
    if root.is_file():
        return _sha256_file(root)
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "."],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if tracked.returncode == 0:
        paths = [root / item.decode("utf-8") for item in tracked.stdout.split(b"\0") if item]
    else:
        volatile = {
            ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache",
            ".ruff_cache", "reports", "downloads", "tmp",
        }
        paths = [
            item for item in root.rglob("*")
            if item.is_file() and volatile.isdisjoint(item.relative_to(root).parts)
        ]
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    readiness_parser = subparsers.add_parser("readiness")
    readiness_parser.add_argument("file", type=Path)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--dsl", required=True, type=Path)
    run_parser.add_argument("--run-dir", required=True, type=Path)
    run_parser.add_argument("--readiness-file", required=True, type=Path)
    run_parser.add_argument("--verification-manifest", required=True, type=Path)
    run_parser.add_argument("--step-timeout-seconds", type=int, default=120)
    run_parser.add_argument("--case-timeout-seconds", type=int, default=900)
    run_parser.add_argument("--run-timeout-seconds", type=int, default=1800)
    run_parser.add_argument("--forward-strip-prefix", action="append", default=[])
    run_parser.add_argument("--cleanup-dsl", type=Path)
    run_parser.add_argument("--var", dest="variable_overrides", action="append", default=[])
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--run-dir", required=True, type=Path)
    inspect_parser.add_argument("--business-id", required=True)
    result_parser = subparsers.add_parser("write-result")
    result_parser.add_argument("--input", required=True, type=Path)
    result_parser.add_argument("--output", required=True, type=Path)
    fingerprint_parser = subparsers.add_parser("fingerprint")
    fingerprint_parser.add_argument("root", type=Path)
    args = parser.parse_args()
    if args.command == "readiness":
        output = check_readiness(json.loads(args.file.read_text(encoding="utf-8"))["readiness"])
    elif args.command == "run":
        output = run_observed(
            dsl=args.dsl,
            run_dir=args.run_dir,
            readiness_file=args.readiness_file,
            verification_manifest=args.verification_manifest,
            step_timeout_seconds=args.step_timeout_seconds,
            case_timeout_seconds=args.case_timeout_seconds,
            run_timeout_seconds=args.run_timeout_seconds,
            forward_strip_prefix=args.forward_strip_prefix,
            cleanup_dsl=args.cleanup_dsl,
            variable_overrides=args.variable_overrides,
        )
    elif args.command == "inspect":
        output = filter_relevant_requests(args.run_dir, args.business_id)
    elif args.command == "write-result":
        output = validate_verification_result(json.loads(args.input.read_text(encoding="utf-8")))
        atomic_write_json(args.output, output)
    else:
        output = {"root": str(args.root), "sha256": directory_fingerprint(args.root)}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
