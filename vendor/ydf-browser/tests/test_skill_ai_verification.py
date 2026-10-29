from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path
import subprocess

import pytest


SKILL_ROOT = Path(__file__).parents[1] / "skills" / "gov-ydfdev-browser"


def _load_ai_verification_module():
    path = SKILL_ROOT / "scripts" / "ai_verification.py"
    spec = importlib.util.spec_from_file_location("skill_ai_verification", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ai_verification_examples_do_not_promote_green_execution_without_api_evidence() -> None:
    payload = json.loads((SKILL_ROOT / "references" / "ai-verification-examples.json").read_text(encoding="utf-8"))

    assert {item["name"] for item in payload["cases"]} == {
        "green_missing_response_body",
        "green_without_local_forward_hit",
    }
    for item in payload["cases"]:
        assert item["expected"]["tool_outcome"] == "passed"
        assert item["expected"]["verification_status"] == "not_verified"
        assert item["expected"]["reason_code"] == "evidence_unavailable"
        assert item["expected"]["business_root_cause_allowed"] is False


def test_ai_skill_requires_installed_doctor_preflight_and_observed_run() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    reference = (SKILL_ROOT / "references" / "ai-verification.md").read_text(encoding="utf-8")

    assert "doctor --skip-config" in reference
    assert "ydf-browser run" in reference
    assert "--source-root" not in reference
    assert "--ai-observe" in reference
    assert "--report-file" in reference
    assert "--verification-manifest" in reference
    assert "不得从转发路径" in reference
    assert "Temporary logging, probes, instrumentation" in reference
    assert "stop as blocked" in reference
    assert "AI business development verification" in skill


def test_ai_doctor_preflight_blocks_incompatible_runtime_skill(tmp_path) -> None:
    module = _load_ai_verification_module()
    cli = tmp_path / "ydf-browser"
    cli.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "print(json.dumps({\"tool_version\": \"0.1.25\", \"contract_version\": \"1.1\", "
        "\"capabilities\": {\"available\": list(%r)}, "
        "\"checks\": {\"skill_compatibility\": {\"ok\": False, \"status\": \"incompatible\"}}}))\n"
        % sorted(module.REQUIRED_CAPABILITIES),
        encoding="utf-8",
    )
    cli.chmod(0o755)

    with pytest.raises(RuntimeError, match="skill is incompatible"):
        module.doctor_preflight(str(cli))


def test_installed_helper_uses_one_path_cli_for_doctor_and_observed_run(
    tmp_path, monkeypatch
) -> None:
    module = _load_ai_verification_module()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    invocation_log = tmp_path / "invocations.jsonl"
    cli = bin_dir / "ydf-browser"
    cli.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

with Path(os.environ["FAKE_YDF_LOG"]).open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}) + "\\n")

if sys.argv[1:] == ["doctor", "--skip-config"]:
    print(json.dumps({
        "tool_version": "9.8.7",
        "contract_version": "1.0",
        "capabilities": {"available": [
            "semantic_events",
            "controlled_timeouts",
            "failure_evidence_bundle",
            "network_text_bodies",
            "network_redaction",
            "request_forward_provenance",
            "case_console_page_errors",
            "table_assertion_snapshot",
            "business_assertion_receipts",
            "notification_request_associations",
            "verification_entrypoint",
            "atomic_evidence_writes"
        ]}
    }))
elif sys.argv[1] == "run":
    report = Path(sys.argv[sys.argv.index("--report-file") + 1])
    report.write_text("{}", encoding="utf-8")
    (report.parent / "events.jsonl").write_text("{}\\n", encoding="utf-8")
else:
    raise SystemExit(2)
""",
        encoding="utf-8",
    )
    cli.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_YDF_LOG", str(invocation_log))
    monkeypatch.setattr(module, "check_readiness", lambda _items: [{"target": "local", "ready": True}])
    monkeypatch.setattr(
        module,
        "verify_frozen_fingerprints",
        lambda *_args: {"verified": True, "actual": {"helper_sha256": "a" * 64}},
    )

    readiness_file = tmp_path / "readiness.json"
    readiness_file.write_text(json.dumps({"readiness": [{}]}), encoding="utf-8")
    dsl = tmp_path / "case.yaml"
    dsl.write_text("suite: {}\n", encoding="utf-8")
    manifest_file = tmp_path / "verification-manifest.json"
    manifest_file.write_text(
        json.dumps(
            {
                "inputs": {"dsl": str(dsl), "readiness": str(readiness_file)},
                "baseline": {
                    "business_repo_head": "abc",
                    "business_repo_porcelain": [],
                    "file_sha256": {},
                },
                "fingerprints": {
                    "release_package_sha256": "package",
                    "ydf_browser": "tool",
                    "agents_skill": "agents",
                    "codex_skill": "codex",
                    "helper_sha256": "helper",
                },
            }
        ),
        encoding="utf-8",
    )

    result = module.run_observed(
        dsl=dsl,
        run_dir=tmp_path / "private-run",
        readiness_file=readiness_file,
        verification_manifest=manifest_file,
        step_timeout_seconds=1,
        case_timeout_seconds=2,
        run_timeout_seconds=3,
        forward_strip_prefix=[],
    )

    assert [item["argv"][0] for item in map(json.loads, invocation_log.read_text().splitlines())] == [
        "doctor",
        "run",
    ]
    assert {key: value for key, value in result["doctor"].items() if key != "capabilities"} == {
        "executable_path": str(cli),
        "executable_realpath": str(cli.resolve()),
        "tool_version": "9.8.7",
        "contract_version": "1.0",
    }
    assert set(result["doctor"]["capabilities"]["available"]) == {
        "semantic_events",
        "controlled_timeouts",
        "failure_evidence_bundle",
        "network_text_bodies",
        "network_redaction",
        "request_forward_provenance",
        "case_console_page_errors",
        "table_assertion_snapshot",
        "business_assertion_receipts",
        "notification_request_associations",
        "verification_entrypoint",
        "atomic_evidence_writes",
    }


def test_readiness_contract_requires_explicit_target_url_timeout_and_tls() -> None:
    module = _load_ai_verification_module()

    assert module.validate_readiness_items(
        [
            {
                "target": "frontend",
                "mode": "http_reachable",
                "url": "https://127.0.0.1:3006/",
                "timeout_seconds": 10,
                "tls_verify": False,
            },
            {
                "target": "backend",
                "mode": "semantic_probe",
                "url": "http://127.0.0.1:62871/_yms/ready",
                "timeout_seconds": 120,
                "tls_verify": True,
                "expected_status": 200,
                "json_path": "$.ready",
                "equals": True,
            },
        ]
    )[0]["target"] == "frontend"

    with pytest.raises(ValueError, match="tls_verify"):
        module.validate_readiness_items(
            [
                {
                    "target": "unknown",
                    "mode": "http_reachable",
                    "url": "http://127.0.0.1:1/",
                    "timeout_seconds": 1,
                }
            ]
        )


def test_verification_result_gate_rejects_verified_without_all_required_runs_and_cleanup() -> None:
    module = _load_ai_verification_module()
    incomplete = {
        "status": "verified",
        "reason_code": "all_gates_passed",
        "runs": [{"phase": "red", "qualified": True}, {"phase": "green", "qualified": True}],
        "cleanup": {"success": True},
        "fingerprints": {"verified": True},
    }

    with pytest.raises(ValueError, match="two qualified green runs"):
        module.validate_verification_result(incomplete)


def test_verification_result_gate_requires_one_locked_dsl_content(tmp_path) -> None:
    module = _load_ai_verification_module()
    result = _verified_result(tmp_path=tmp_path, module=module)

    result["runs"][1]["dsl_sha256"] = "1" * 64
    with pytest.raises(ValueError, match="same DSL content"):
        module.validate_verification_result(result)


def test_verification_result_gate_requires_complete_same_run_flow_and_fresh_ids(tmp_path) -> None:
    module = _load_ai_verification_module()
    result = _verified_result(tmp_path=tmp_path, module=module)

    assert module.validate_verification_result(result) == result

    result["runs"][2]["api_business_id"] = "AI-G1"
    result["runs"][2]["ui_business_id"] = "AI-G1"
    with pytest.raises(ValueError, match="fresh business identifiers"):
        module.validate_verification_result(result)

    result = _verified_result(tmp_path=tmp_path / "missing-flow", module=module)
    index = Path(result["runs"][0]["run_dir"]) / "artifacts" / "network" / "index.jsonl"
    records = [json.loads(line) for line in index.read_text(encoding="utf-8").splitlines()]
    index.write_text(
        "\n".join(json.dumps(item) for item in records if item["request_id"] != "request-mutation"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="same run directory"):
        module.validate_verification_result(result)

    result = _verified_result(tmp_path=tmp_path / "negative-postcondition", module=module)
    red = result["runs"][0]
    postcondition_id = red["flow_request_ids"]["postcondition"]
    postcondition_body = Path(red["run_dir"]) / "artifacts" / "network" / postcondition_id / "request-body.json"
    postcondition_body.write_text(json.dumps({"content": {"recordList": []}}), encoding="utf-8")
    assert module.validate_verification_result(result) == result

    red["assertion_receipt"]["candidate_request_ids"] = []
    report = Path(red["run_dir"]) / "report.json"
    report_payload = json.loads(report.read_text(encoding="utf-8"))
    report_payload["assertion_receipt"] = red["assertion_receipt"]
    report.write_text(json.dumps(report_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="carry the same business identifier"):
        module.validate_verification_result(result)


def test_verification_result_gate_rejects_qualified_run_without_helper_and_cleanup_evidence(
    tmp_path,
) -> None:
    module = _load_ai_verification_module()
    result = _verified_result(tmp_path=tmp_path, module=module)
    external_path = Path(result["runs"][0]["run_dir"]) / "external-result.json"
    external = json.loads(external_path.read_text(encoding="utf-8"))
    external.pop("verification")
    external_path.write_text(json.dumps(external), encoding="utf-8")

    with pytest.raises(ValueError, match="frozen skill helper"):
        module.validate_verification_result(result)


def test_frozen_fingerprint_gate_reports_each_mismatch() -> None:
    module = _load_ai_verification_module()

    with pytest.raises(RuntimeError, match="agents_skill, helper_sha256"):
        module.validate_frozen_fingerprints(
            {
                "ydf_browser": "tool",
                "agents_skill": "agents-before",
                "helper_sha256": "helper-before",
            },
            {
                "ydf_browser": "tool",
                "agents_skill": "agents-after",
                "helper_sha256": "helper-after",
            },
        )


def test_frozen_fingerprint_gate_uses_only_the_canonical_agents_skill(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_ai_verification_module()
    agents_home = tmp_path / "agents"
    canonical = agents_home / "skills" / "gov-ydfdev-browser"
    helper = canonical / "scripts" / "ai_verification.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("canonical helper\n", encoding="utf-8")
    (canonical / "SKILL.md").write_text("canonical skill\n", encoding="utf-8")
    executable = tmp_path / "bin" / "ydf-browser"
    executable.parent.mkdir()
    executable.write_text("runtime\n", encoding="utf-8")
    monkeypatch.setenv("AGENTS_HOME", str(agents_home))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "missing-codex"))
    monkeypatch.setattr(module, "__file__", str(helper))
    expected = {
        "ydf_browser": module._sha256_file(executable),
        "agents_skill": module.directory_fingerprint(canonical),
        "helper_sha256": module._sha256_file(helper),
    }

    result = module.verify_frozen_fingerprints(
        {"fingerprints": expected},
        str(executable),
    )

    assert result == {"verified": True, "actual": expected}


def test_cleanup_dsl_retries_once_and_keeps_attempt_evidence(tmp_path, monkeypatch) -> None:
    module = _load_ai_verification_module()
    outcomes = iter([False, True])

    def fake_run(_command, *, timeout_seconds, environment):
        report_file = Path(_command[_command.index("--report-file") + 1])
        report_file.parent.mkdir(parents=True)
        success = next(outcomes)
        report_file.write_text(json.dumps({"success": success}), encoding="utf-8")
        return {"returncode": 0 if success else 1, "outcome": "completed", "reason_code": None}

    monkeypatch.setattr(module, "run_cli_process", fake_run)

    result = module.run_cleanup(
        executable="ydf-browser",
        cleanup_dsl=tmp_path / "cleanup.yaml",
        cleanup_root=tmp_path / "cleanup",
        step_timeout_seconds=1,
        case_timeout_seconds=2,
        run_timeout_seconds=3,
        forward_strip_prefix=[],
        variable_overrides=["business_id=AI-001"],
        environment={"YDF_BROWSER_AUTO_UPDATE": "0"},
    )

    assert result["success"] is True
    assert [item["attempt"] for item in result["attempts"]] == [1, 2]
    assert result["attempts"][0]["report"] == "cleanup/attempt-1/report.json"
    assert result["attempts"][1]["report"] == "cleanup/attempt-2/report.json"


def _verified_result(*, tmp_path: Path, module) -> dict:
    dsl_sha256 = "0" * 64
    runs = [
        _qualified_run(tmp_path / "red", "red", "AI-R", "assertion_failed", dsl_sha256),
        _qualified_run(tmp_path / "green-1", "green", "AI-G1", "passed", dsl_sha256),
        _qualified_run(tmp_path / "green-2", "green", "AI-G2", "passed", dsl_sha256),
    ]
    return {
        "status": "verified",
        "reason_code": "all_gates_passed",
        "runs": runs,
        "cleanup": {"success": True, "identifiers": ["AI-R", "AI-G1", "AI-G2"]},
        "fingerprints": {"verified": True},
    }


def _qualified_run(run_dir: Path, phase: str, business_id: str, outcome: str, dsl_sha256: str) -> dict:
    network = run_dir / "artifacts" / "network"
    network.mkdir(parents=True)
    request_ids = {
        "precondition": "request-precondition",
        "mutation": "request-mutation",
        "postcondition": "request-postcondition",
    }
    records = []
    for sequence, request_id in enumerate(request_ids.values(), start=1):
        body_dir = network / request_id
        body_dir.mkdir()
        (body_dir / "request-body.json").write_text(
            json.dumps({"content": {"business_id": business_id}}),
            encoding="utf-8",
        )
        records.append(
            {
                "event": "request_completed",
                "request_id": request_id,
                "sequence": sequence,
                "request_body": {"path": f"artifacts/network/{request_id}/request-body.json"},
                "forwarding": {"matched": True, "success": True},
            }
        )
    (network / "index.jsonl").write_text(
        "\n".join(json.dumps(item) for item in records),
        encoding="utf-8",
    )
    assertion_receipt = {
        "expected": business_id,
        "candidate_request_ids": [request_ids["postcondition"]],
    }
    (run_dir / "report.json").write_text(
        json.dumps(
            {
                "run": {
                    "verification": {
                        "entrypoint": "skill_helper",
                        "verification_eligible": True,
                        "helper_sha256": "helper",
                        "status": "not_evaluated",
                    }
                },
                "assertion_receipt": assertion_receipt,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "external-result.json").write_text(
        json.dumps(
            {
                "dsl": {"sha256": dsl_sha256},
                "report": "report.json",
                "verification": {
                    "entrypoint": "skill_helper",
                    "verification_eligible": True,
                    "helper_sha256": "helper",
                },
                "fingerprints": {"verified": True, "actual": {"helper_sha256": "helper"}},
                "cleanup": {"success": True},
            }
        ),
        encoding="utf-8",
    )
    return {
        "phase": phase,
        "qualified": True,
        "dsl_sha256": dsl_sha256,
        "run_dir": str(run_dir.resolve()),
        "tool_outcome": outcome,
        "report": str(run_dir / "report.json"),
        "assertion_receipt": assertion_receipt,
        "request_id": request_ids["postcondition"],
        "flow_request_ids": request_ids,
        "api_business_id": business_id,
        "ui_business_id": business_id,
        "local_forward_hit": True,
    }


def test_skill_external_watchdog_terminates_then_uses_only_flushed_evidence(tmp_path, monkeypatch) -> None:
    module = _load_ai_verification_module()
    executable = tmp_path / "bin" / "ydf-browser"
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")
    readiness_file = tmp_path / "readiness.json"
    readiness_file.write_text(json.dumps({"readiness": [{}]}), encoding="utf-8")
    dsl = tmp_path / "case.yaml"
    dsl.write_text("suite: {}\n", encoding="utf-8")
    manifest_file = tmp_path / "verification-manifest.json"
    manifest_file.write_text(
        json.dumps(
            {
                "inputs": {"dsl": str(tmp_path / "case.yaml"), "readiness": str(readiness_file)},
                "baseline": {
                    "business_repo_head": "abc",
                    "business_repo_porcelain": [],
                    "file_sha256": {},
                },
                "fingerprints": {
                    "release_package_sha256": "package",
                    "ydf_browser": "tool",
                    "agents_skill": "agents",
                    "codex_skill": "codex",
                    "helper_sha256": "helper",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "doctor_preflight",
        lambda _executable: {"tool_version": "test", "contract_version": "1.0"},
    )
    monkeypatch.setattr(module, "installed_cli", lambda: (str(executable), str(executable.resolve())))
    monkeypatch.setattr(module, "check_readiness", lambda _items: [{"target": "local", "ready": True}])
    monkeypatch.setattr(
        module,
        "verify_frozen_fingerprints",
        lambda *_args: {"verified": True, "actual": {"helper_sha256": "a" * 64}},
    )

    class FakeProcess:
        returncode = -15

        def __init__(self):
            self.communicate_calls = 0
            self.terminated = False
            self.killed = False

        def communicate(self, timeout=None):
            self.communicate_calls += 1
            if self.communicate_calls == 1:
                raise subprocess.TimeoutExpired("ydf-browser", timeout)
            return "", ""

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True

    process = FakeProcess()
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: process)
    run_dir = tmp_path / "private-run"

    result = module.run_observed(
        dsl=dsl,
        run_dir=run_dir,
        readiness_file=readiness_file,
        verification_manifest=manifest_file,
        step_timeout_seconds=1,
        case_timeout_seconds=2,
        run_timeout_seconds=3,
        forward_strip_prefix=[],
    )

    assert process.terminated is True
    assert process.killed is False
    assert result["outcome"] == "terminated"
    assert result["reason_code"] == "external_termination"
    persisted = json.loads((run_dir / "external-result.json").read_text(encoding="utf-8"))
    assert persisted["report"] is None
    assert persisted["events"] is None
    assert persisted["verification_manifest"]["sha256"]
    assert persisted["dsl"] == {
        "path": str(dsl.resolve()),
        "sha256": module.hashlib.sha256(dsl.read_bytes()).hexdigest(),
    }


def test_skill_rejects_missing_or_mismatched_manifest_before_observed_run(tmp_path) -> None:
    module = _load_ai_verification_module()
    dsl = tmp_path / "case.yaml"
    readiness = tmp_path / "readiness.json"
    manifest = tmp_path / "verification-manifest.json"

    with pytest.raises(ValueError, match="manifest not found"):
        module.load_verification_manifest(manifest, dsl=dsl, readiness_file=readiness)

    manifest.write_text(
        json.dumps(
            {
                "inputs": {"dsl": str(tmp_path / "other.yaml"), "readiness": str(readiness)},
                "baseline": {
                    "business_repo_head": "abc",
                    "business_repo_porcelain": [],
                    "file_sha256": {},
                },
                "fingerprints": {
                    "release_package_sha256": "package",
                    "ydf_browser": "tool",
                    "agents_skill": "agents",
                    "codex_skill": "codex",
                    "helper_sha256": "helper",
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="inputs.dsl"):
        module.load_verification_manifest(manifest, dsl=dsl, readiness_file=readiness)


def test_manifest_requires_release_package_and_installed_helper_fingerprints(tmp_path) -> None:
    module = _load_ai_verification_module()
    dsl = tmp_path / "case.yaml"
    readiness = tmp_path / "readiness.json"
    manifest = tmp_path / "verification-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "inputs": {"dsl": str(dsl), "readiness": str(readiness)},
                "baseline": {
                    "business_repo_head": "abc",
                    "business_repo_porcelain": [],
                    "file_sha256": {},
                },
                "fingerprints": {
                    "ydf_browser": "tool",
                    "agents_skill": "agents",
                    "codex_skill": "codex",
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="helper_sha256, release_package_sha256"):
        module.load_verification_manifest(manifest, dsl=dsl, readiness_file=readiness)


def test_manifest_accepts_one_canonical_skill_fingerprint(tmp_path) -> None:
    module = _load_ai_verification_module()
    dsl = tmp_path / "case.yaml"
    readiness = tmp_path / "readiness.json"
    manifest = tmp_path / "verification-manifest.json"
    payload = {
        "inputs": {"dsl": str(dsl), "readiness": str(readiness)},
        "baseline": {
            "business_repo_head": "abc",
            "business_repo_porcelain": [],
            "file_sha256": {},
        },
        "fingerprints": {
            "release_package_sha256": "package",
            "ydf_browser": "tool",
            "agents_skill": "agents",
            "helper_sha256": "helper",
        },
    }
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    loaded, _sha256 = module.load_verification_manifest(
        manifest,
        dsl=dsl,
        readiness_file=readiness,
    )

    assert loaded == payload


def test_skill_filters_only_assertion_candidates_with_matching_api_ui_identity_and_forward_hit(tmp_path) -> None:
    module = _load_ai_verification_module()
    run_dir = tmp_path / "run"
    body_dir = run_dir / "artifacts" / "network" / "request-000001"
    body_dir.mkdir(parents=True)
    (body_dir / "response-body.json").write_text(
        json.dumps({"content": {"code": "AI-001"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "report.json").write_text(
        json.dumps(
            {
                "observation": {
                    "assertion_receipt": {
                        "candidate_request_ids": ["request-000001"],
                        "actual": {"values": ["AI-001"]},
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    index = run_dir / "artifacts" / "network" / "index.jsonl"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(
        "\n".join(
            [
                json.dumps({"event": "request_started", "request_id": "request-000001"}),
                json.dumps(
                    {
                        "event": "request_completed",
                        "request_id": "request-000001",
                        "actual_url": "http://127.0.0.1:62871/fbdi-be/query",
                        "status": 200,
                        "response_body": {"path": "artifacts/network/request-000001/response-body.json"},
                        "forwarding": {"matched": True, "success": True},
                    }
                ),
                json.dumps(
                    {
                        "event": "request_completed",
                        "request_id": "request-999999",
                        "status": 200,
                        "forwarding": {"matched": True, "success": True},
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    result = module.filter_relevant_requests(run_dir, "AI-001")

    assert result["ui_identity_matched"] is True
    assert [item["request_id"] for item in result["requests"]] == ["request-000001"]
    assert result["requests"][0]["api_identity_matched"] is True
    assert result["requests"][0]["local_forward_hit"] is True


def test_skill_contains_machine_readable_manifest_and_result_schemas() -> None:
    manifest = json.loads(
        (SKILL_ROOT / "references" / "verification-manifest.schema.json").read_text(encoding="utf-8")
    )
    result = json.loads(
        (SKILL_ROOT / "references" / "verification-result.schema.json").read_text(encoding="utf-8")
    )

    assert {"inputs", "baseline", "fingerprints"} <= set(manifest["required"])
    assert {"dsl", "cleanup_dsl", "readiness"} <= set(
        manifest["properties"]["inputs"]["required"]
    )
    assert set(manifest["properties"]["fingerprints"]["required"]) == {
        "release_package_sha256",
        "ydf_browser",
        "agents_skill",
        "helper_sha256",
    }
    assert {"status", "reason_code", "runs", "cleanup", "fingerprints"} <= set(result["required"])
    assert "dsl_sha256" in result["properties"]["runs"]["items"]["required"]
    assert "flow_request_ids" in result["properties"]["runs"]["items"]["required"]
    assert result["properties"]["status"]["enum"] == ["verified", "not_verified", "invalid"]
    examples = json.loads(
        (SKILL_ROOT / "references" / "verification-result.examples.json").read_text(encoding="utf-8")
    )
    assert {item["status"] for item in examples} == {"verified", "not_verified", "invalid"}
    cleanup_failed = next(item for item in examples if item["reason_code"] == "cleanup_failed")
    assert cleanup_failed["business_assertions_passed"] is True
    assert cleanup_failed["cleanup"]["success"] is False
    assert cleanup_failed["cleanup"]["identifiers"]


def test_directory_fingerprint_ignores_git_metadata_and_ignored_runtime_artifacts(
    tmp_path,
) -> None:
    module = _load_ai_verification_module()
    root = tmp_path / "source"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / ".gitignore").write_text("reports/\n.pytest_cache/\n", encoding="utf-8")
    source = root / "source.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore", "source.py"], cwd=root, check=True)
    before = module.directory_fingerprint(root)

    (root / "reports").mkdir()
    (root / "reports" / "report.json").write_text("{}", encoding="utf-8")
    (root / ".pytest_cache").mkdir()
    (root / ".pytest_cache" / "nodeids").write_text("[]", encoding="utf-8")
    subprocess.run(["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True)

    assert module.directory_fingerprint(root) == before
    source.write_text("VALUE = 2\n", encoding="utf-8")
    assert module.directory_fingerprint(root) != before


def test_directory_fingerprint_hashes_a_file_directly(tmp_path) -> None:
    module = _load_ai_verification_module()
    executable = tmp_path / "ydf-browser"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")

    assert module.directory_fingerprint(executable) == module.hashlib.sha256(
        executable.read_bytes()
    ).hexdigest()
