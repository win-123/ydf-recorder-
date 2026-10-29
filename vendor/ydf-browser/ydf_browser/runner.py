from __future__ import annotations

import fnmatch
import glob
import shutil
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import DslTestCase, DslTestSuite, ExecutionReport, StepResult
from .variables import RuntimeVariableContext

DSL_SUFFIXES = {".yaml", ".yml", ".json"}
FAILURE_POLICIES = {"continue", "stop_suite", "stop_run"}


@dataclass(slots=True)
class SuiteRunSpec:
    dsl_path: Path
    suite: DslTestSuite
    cases: list[DslTestCase]


@dataclass(slots=True)
class CaseRunSpec:
    dsl_path: Path
    suite: DslTestSuite
    case: DslTestCase
    suite_index: int
    case_index: int
    total_cases: int
    runtime_context: RuntimeVariableContext | None = None


@dataclass
class _SuiteState:
    spec: SuiteRunSpec
    suite_index: int
    policy: str
    next_case_index: int = 0
    running: int = 0
    case_reports: dict[int, dict[str, Any]] = field(default_factory=dict)
    runtime_context: RuntimeVariableContext = field(default_factory=RuntimeVariableContext)

    @property
    def done(self) -> bool:
        return self.next_case_index >= len(self.spec.cases) and self.running == 0

    def can_schedule(self) -> bool:
        if self.next_case_index >= len(self.spec.cases):
            return False
        if self.policy in {"stop_suite", "stop_run"} and self.running:
            return False
        if getattr(self.spec.suite, "requires_runtime_serial", False) and self.running:
            return False
        return True


def discover_dsl_files(inputs: list[str]) -> list[Path]:
    discovered: list[Path] = []
    for item in inputs:
        path = Path(item).expanduser()
        if path.exists():
            discovered.extend(_discover_existing_path(path))
            continue
        matches = [Path(match).expanduser() for match in glob.glob(item, recursive=True)]
        if not matches:
            raise FileNotFoundError(f"未找到 DSL: {item}")
        for match in matches:
            discovered.extend(_discover_existing_path(match))
    deduped: dict[Path, Path] = {}
    for path in discovered:
        resolved = path.resolve()
        if resolved not in deduped:
            deduped[resolved] = path
    return list(deduped.values())


def _discover_existing_path(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() not in DSL_SUFFIXES:
            raise ValueError(f"不支持的 DSL 文件类型: {path}")
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(f"未找到 DSL: {path}")
    files = [item for item in path.rglob("*") if item.is_file() and item.suffix.lower() in DSL_SUFFIXES]
    return sorted(files, key=lambda value: str(value))


def filter_cases(
    cases: list[DslTestCase],
    *,
    case_codes: list[str] | None = None,
    case_globs: list[str] | None = None,
    grep: str | None = None,
    tags: list[str] | None = None,
) -> list[DslTestCase]:
    return [
        case
        for case in cases
        if _matches_case_filters(
            case,
            case_codes=case_codes or [],
            case_globs=case_globs or [],
            grep=(grep or "").strip(),
            tags=tags or [],
        )
    ]


def _matches_case_filters(
    case: DslTestCase,
    *,
    case_codes: list[str],
    case_globs: list[str],
    grep: str,
    tags: list[str],
) -> bool:
    if case_codes and case.code not in case_codes:
        return False
    if case_globs and not any(fnmatch.fnmatchcase(case.code, pattern) for pattern in case_globs):
        return False
    if grep and grep not in f"{case.code}\n{case.name}\n{case.description}":
        return False
    if tags and not set(tags).intersection(case.tags):
        return False
    return True


def run_suite_specs(
    suite_specs: list[SuiteRunSpec],
    *,
    run_case: Callable[[CaseRunSpec], ExecutionReport],
    concurrency: int = 1,
    run_id: str | None = None,
    started_at: str | None = None,
    metadata: dict[str, Any] | None = None,
    on_suite_start: Callable[[SuiteRunSpec], None] | None = None,
    on_case_start: Callable[[CaseRunSpec], None] | None = None,
    on_case_result: Callable[[CaseRunSpec, ExecutionReport], None] | None = None,
) -> dict[str, Any]:
    if concurrency < 1:
        raise ValueError("--concurrency 必须大于等于 1")
    started_monotonic = time.monotonic()
    run_started_at = started_at or _now_iso()
    effective_run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    states = [
        _SuiteState(spec=spec, suite_index=index, policy=_normalize_policy(spec.suite.on_case_failure))
        for index, spec in enumerate(suite_specs)
    ]
    for spec in suite_specs:
        if on_suite_start:
            on_suite_start(spec)
    if concurrency == 1:
        return _run_suite_specs_serial(
            states,
            run_case=run_case,
            started_monotonic=started_monotonic,
            run_started_at=run_started_at,
            effective_run_id=effective_run_id,
            metadata=metadata,
            on_case_start=on_case_start,
            on_case_result=on_case_result,
        )
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures: dict[Future[ExecutionReport], tuple[_SuiteState, CaseRunSpec, float, str]] = {}
        stop_run = False
        stop_reason = ""
        _schedule_ready_cases(executor, states, futures, run_case, concurrency, on_case_start, stop_run)
        while futures:
            done, _pending = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                state, case_spec, case_started_monotonic, case_started_at = futures.pop(future)
                state.running -= 1
                report = _future_report(future)
                case_report = _case_report_payload(
                    case_spec,
                    report,
                    status="passed" if report.success else "failed",
                    started_at=case_started_at,
                    duration_ms=_elapsed_ms(case_started_monotonic),
                )
                state.case_reports[case_spec.case_index - 1] = case_report
                if on_case_result:
                    on_case_result(case_spec, report)
                if not report.success:
                    if state.policy == "stop_suite":
                        _skip_remaining_suite_cases(
                            state,
                            f"suite stopped after failed case: {case_spec.case.code}",
                        )
                    elif state.policy == "stop_run":
                        stop_run = True
                        stop_reason = f"run stopped after failed case: {case_spec.case.code}"
                        for item in states:
                            _skip_remaining_suite_cases(item, stop_reason)
            _schedule_ready_cases(executor, states, futures, run_case, concurrency, on_case_start, stop_run)
    suite_reports = [_suite_report_payload(state) for state in states]
    totals = _totals(suite_reports)
    run_payload = {
        "id": effective_run_id,
        "started_at": run_started_at,
        "ended_at": _now_iso(),
        "duration_ms": _elapsed_ms(started_monotonic),
        "concurrency": concurrency,
    }
    if metadata:
        run_payload.update(metadata)
    if stop_reason:
        run_payload["stop_reason"] = stop_reason
    observation = _aggregate_observations(suite_reports)
    if observation is not None:
        run_payload["observation"] = observation
    return {
        "success": totals["failed"] == 0 and totals["skipped"] == 0,
        "run": run_payload,
        "totals": totals,
        "suite_reports": suite_reports,
    }


def _run_suite_specs_serial(
    states: list[_SuiteState],
    *,
    run_case: Callable[[CaseRunSpec], ExecutionReport],
    started_monotonic: float,
    run_started_at: str,
    effective_run_id: str,
    metadata: dict[str, Any] | None,
    on_case_start: Callable[[CaseRunSpec], None] | None,
    on_case_result: Callable[[CaseRunSpec, ExecutionReport], None] | None,
) -> dict[str, Any]:
    stop_run = False
    stop_reason = ""
    while not stop_run:
        state = _next_schedulable_state(states)
        if state is None:
            break
        case_index = state.next_case_index
        case = state.spec.cases[case_index]
        state.next_case_index += 1
        state.running += 1
        case_spec = CaseRunSpec(
            dsl_path=state.spec.dsl_path,
            suite=state.spec.suite,
            case=case,
            suite_index=state.suite_index + 1,
            case_index=case_index + 1,
            total_cases=len(state.spec.cases),
            runtime_context=state.runtime_context,
        )
        if on_case_start:
            on_case_start(case_spec)
        case_started = time.monotonic()
        case_started_at = _now_iso()
        report = _run_case_safely(run_case, case_spec)
        state.running -= 1
        case_report = _case_report_payload(
            case_spec,
            report,
            status="passed" if report.success else "failed",
            started_at=case_started_at,
            duration_ms=_elapsed_ms(case_started),
        )
        state.case_reports[case_spec.case_index - 1] = case_report
        if on_case_result:
            on_case_result(case_spec, report)
        if report.success:
            continue
        if state.policy == "stop_suite":
            _skip_remaining_suite_cases(
                state,
                f"suite stopped after failed case: {case_spec.case.code}",
            )
        elif state.policy == "stop_run":
            stop_run = True
            stop_reason = f"run stopped after failed case: {case_spec.case.code}"
            for item in states:
                _skip_remaining_suite_cases(item, stop_reason)
    suite_reports = [_suite_report_payload(state) for state in states]
    totals = _totals(suite_reports)
    run_payload = {
        "id": effective_run_id,
        "started_at": run_started_at,
        "ended_at": _now_iso(),
        "duration_ms": _elapsed_ms(started_monotonic),
        "concurrency": 1,
    }
    if metadata:
        run_payload.update(metadata)
    if stop_reason:
        run_payload["stop_reason"] = stop_reason
    observation = _aggregate_observations(suite_reports)
    if observation is not None:
        run_payload["observation"] = observation
    return {
        "success": totals["failed"] == 0 and totals["skipped"] == 0,
        "run": run_payload,
        "totals": totals,
        "suite_reports": suite_reports,
    }


def archive_diagnostic_files(result: dict[str, Any], report_dir: Path) -> None:
    artifact_root = report_dir / "artifacts"
    for suite_report in result.get("suite_reports", []):
        suite_code = _safe_path_part((suite_report.get("suite") or {}).get("code") or "suite")
        for case_report in suite_report.get("case_reports", []):
            report = case_report.get("report")
            if not isinstance(report, dict):
                continue
            case_code = _safe_path_part((case_report.get("case") or {}).get("code") or "case")
            case_artifact_dir = artifact_root / suite_code / case_code
            for step_result in report.get("step_results", []):
                data = step_result.get("data") if isinstance(step_result, dict) else None
                if not isinstance(data, dict):
                    continue
                archived = _archive_step_diagnostics(data.get("diagnostic_files"), case_artifact_dir)
                if archived:
                    data["archived_diagnostic_files"] = archived


def _archive_step_diagnostics(raw_files: Any, target_dir: Path) -> list[str]:
    if not isinstance(raw_files, list):
        return []
    archived: list[str] = []
    for raw_file in raw_files:
        source = Path(str(raw_file)).expanduser()
        if not source.is_file():
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        target = _unique_target_path(target_dir / source.name)
        shutil.copy2(source, target)
        archived.append(str(target))
    return archived


def _unique_target_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(1, 1000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"无法生成诊断文件归档路径: {path}")


def _safe_path_part(value: Any) -> str:
    text = str(value or "").strip()
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in text)
    return safe if safe not in {"", ".", ".."} else "unknown"


def _schedule_ready_cases(
    executor: ThreadPoolExecutor,
    states: list[_SuiteState],
    futures: dict[Future[ExecutionReport], tuple[_SuiteState, CaseRunSpec, float, str]],
    run_case: Callable[[CaseRunSpec], ExecutionReport],
    concurrency: int,
    on_case_start: Callable[[CaseRunSpec], None] | None,
    stop_run: bool,
) -> None:
    while not stop_run and len(futures) < concurrency:
        state = _next_schedulable_state(states)
        if state is None:
            return
        case_index = state.next_case_index
        case = state.spec.cases[case_index]
        state.next_case_index += 1
        state.running += 1
        case_spec = CaseRunSpec(
            dsl_path=state.spec.dsl_path,
            suite=state.spec.suite,
            case=case,
            suite_index=state.suite_index + 1,
            case_index=case_index + 1,
            total_cases=len(state.spec.cases),
            runtime_context=state.runtime_context,
        )
        if on_case_start:
            on_case_start(case_spec)
        case_started = time.monotonic()
        case_started_at = _now_iso()
        future = executor.submit(run_case, case_spec)
        futures[future] = (state, case_spec, case_started, case_started_at)


def _next_schedulable_state(states: list[_SuiteState]) -> _SuiteState | None:
    for index, state in enumerate(states):
        if not state.can_schedule():
            continue
        if _blocked_by_prior_stop_run_suite(states, index):
            return None
        return state
    return None


def _blocked_by_prior_stop_run_suite(states: list[_SuiteState], index: int) -> bool:
    return any(state.policy == "stop_run" and not state.done for state in states[:index])


def _future_report(future: Future[ExecutionReport]) -> ExecutionReport:
    try:
        return future.result()
    except Exception as exc:
        return _exception_report(exc)


def _run_case_safely(
    run_case: Callable[[CaseRunSpec], ExecutionReport],
    case_spec: CaseRunSpec,
) -> ExecutionReport:
    try:
        return run_case(case_spec)
    except Exception as exc:
        return _exception_report(exc)


def _exception_report(exc: Exception) -> ExecutionReport:
    message = str(exc)
    return ExecutionReport(
        success=False,
        step_results=[
            StepResult(
                action="case",
                success=False,
                message=message,
                data={"error": {"type": exc.__class__.__name__, "message": message}},
            )
        ],
        errors=[message],
    )


def _case_report_payload(
    case_spec: CaseRunSpec,
    report: ExecutionReport,
    *,
    status: str,
    started_at: str,
    duration_ms: int,
) -> dict[str, Any]:
    payload = {
        "dsl_file": str(case_spec.dsl_path),
        "suite_code": case_spec.suite.code,
        "case_index": case_spec.case_index,
        "total_cases": case_spec.total_cases,
        "case": case_spec.case.to_dict(),
        "success": report.success,
        "status": status,
        "started_at": started_at,
        "ended_at": _now_iso(),
        "duration_ms": duration_ms,
        "report": report.to_dict(),
        "errors": report.errors,
    }
    if report.performance is not None:
        payload["performance"] = report.performance
    if report.profile is not None:
        payload["profile"] = report.profile
    if report.bpr_sessions:
        payload["bpr_sessions"] = report.bpr_sessions
    for step in reversed(report.step_results):
        if step.observation is not None:
            payload["observation"] = dict(step.observation)
            break
    return payload


def _skip_remaining_suite_cases(state: _SuiteState, reason: str) -> None:
    while state.next_case_index < len(state.spec.cases):
        case_index = state.next_case_index
        case = state.spec.cases[case_index]
        state.next_case_index += 1
        state.case_reports[case_index] = {
            "dsl_file": str(state.spec.dsl_path),
            "suite_code": state.spec.suite.code,
            "case_index": case_index + 1,
            "total_cases": len(state.spec.cases),
            "case": case.to_dict(),
            "success": False,
            "status": "skipped",
            "skip_reason": reason,
            "report": None,
            "errors": [],
        }


def _suite_report_payload(state: _SuiteState) -> dict[str, Any]:
    reports = [state.case_reports[index] for index in sorted(state.case_reports)]
    totals = _case_totals(reports)
    payload = {
        "dsl_file": str(state.spec.dsl_path),
        "suite": state.spec.suite.to_dict(),
        "success": totals["failed"] == 0 and totals["skipped"] == 0,
        "on_case_failure": state.policy,
        "totals": totals,
        "case_reports": reports,
    }
    observation = _aggregate_observations(reports)
    if observation is not None:
        payload["observation"] = observation
    return payload


def _aggregate_observations(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    observations = [item["observation"] for item in items if isinstance(item.get("observation"), dict)]
    if not observations:
        return None
    priority = {"passed": 0, "blocked": 1, "assertion_failed": 2, "terminated": 3}
    return dict(max(observations, key=lambda item: priority.get(str(item.get("outcome")), 1)))


def _totals(suite_reports: list[dict[str, Any]]) -> dict[str, int]:
    totals = {"suites": len(suite_reports), "cases": 0, "passed": 0, "failed": 0, "skipped": 0}
    for suite_report in suite_reports:
        suite_totals = suite_report["totals"]
        totals["cases"] += suite_totals["cases"]
        totals["passed"] += suite_totals["passed"]
        totals["failed"] += suite_totals["failed"]
        totals["skipped"] += suite_totals["skipped"]
    return totals


def _case_totals(case_reports: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "cases": len(case_reports),
        "passed": sum(1 for item in case_reports if item["status"] == "passed"),
        "failed": sum(1 for item in case_reports if item["status"] == "failed"),
        "skipped": sum(1 for item in case_reports if item["status"] == "skipped"),
    }


def _normalize_policy(policy: str) -> str:
    text = (policy or "continue").strip().replace("-", "_")
    if text not in FAILURE_POLICIES:
        raise ValueError(f"不支持的失败策略: {policy}")
    return text


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _elapsed_ms(started_monotonic: float) -> int:
    return int((time.monotonic() - started_monotonic) * 1000)
