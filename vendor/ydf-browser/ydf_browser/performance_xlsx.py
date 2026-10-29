from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .bpr_report import SERVER_SUMMARY_FIELDS


SHEET_RUN_SUMMARY = "运行汇总"
SHEET_CASE_SUMMARY = "用例汇总"
SHEET_STEP_OVERVIEW = "步骤总览"
SHEET_NETWORK_DETAILS = "网络请求明细"
SHEET_FAILED_REQUESTS = "失败请求详情"
SHEET_DUPLICATE_URLS = "重复调用URL"
SHEET_WEB_VITALS = "Web Vitals评级"
SHEET_BPR_RECORDINGS = "BPR录制"

SHEET_NAMES = [
    SHEET_RUN_SUMMARY,
    SHEET_CASE_SUMMARY,
    SHEET_STEP_OVERVIEW,
    SHEET_NETWORK_DETAILS,
    SHEET_FAILED_REQUESTS,
    SHEET_DUPLICATE_URLS,
    SHEET_WEB_VITALS,
    SHEET_BPR_RECORDINGS,
]


def export_performance_xlsx(result: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    workbook.active.title = SHEET_RUN_SUMMARY
    for name in SHEET_NAMES[1:]:
        workbook.create_sheet(name)

    network_events = _all_network_events(result)
    _write_run_summary(workbook[SHEET_RUN_SUMMARY], result, network_events)
    _write_case_summary(workbook[SHEET_CASE_SUMMARY], result)
    _write_step_overview(workbook[SHEET_STEP_OVERVIEW], result, network_events)
    _write_network_details(workbook[SHEET_NETWORK_DETAILS], network_events)
    _write_failed_requests(workbook[SHEET_FAILED_REQUESTS], network_events)
    _write_duplicate_urls(workbook[SHEET_DUPLICATE_URLS], network_events)
    _write_web_vitals(workbook[SHEET_WEB_VITALS], result)
    _write_bpr_recordings(workbook[SHEET_BPR_RECORDINGS], result)

    for sheet in workbook.worksheets:
        _format_sheet(sheet)
    workbook.save(path)
    return path


def _write_run_summary(sheet, result: dict[str, Any], network_events: list[dict[str, Any]]) -> None:
    run = _dict(result.get("run"))
    totals = _dict(result.get("totals"))
    summary = _dict(_dict(run.get("performance")).get("summary"))
    cache_modes = ", ".join(str(item) for item in _list(_dict(run.get("performance")).get("cache_modes")))
    rows = [
        ("运行ID", run.get("id")),
        ("环境", run.get("env") or run.get("env_name")),
        ("开始时间", run.get("started_at")),
        ("结束时间", run.get("ended_at")),
        ("总耗时(ms)", _int(run.get("duration_ms"))),
        ("测试集数", _int(totals.get("suites"))),
        ("用例数", _int(totals.get("cases"))),
        ("通过用例", _int(totals.get("passed"))),
        ("失败用例", _int(totals.get("failed"))),
        ("跳过用例", _int(totals.get("skipped"))),
        ("总请求数", len(network_events)),
        ("失败请求数", sum(1 for event in network_events if _is_failed_request(event))),
        ("最慢用例", _slow_label(summary.get("slowest_case"))),
        ("最慢步骤", _slow_label(summary.get("slowest_step"))),
        ("缓存模式", cache_modes),
        ("性能文件", result.get("performance_file")),
        ("性能导出错误", _dict(run.get("performance")).get("export_error")),
    ]
    sheet.append(("指标", "值"))
    for row in rows:
        sheet.append(row)


def _write_case_summary(sheet, result: dict[str, Any]) -> None:
    sheet.append(
        (
            "运行ID",
            "测试集",
            "用例",
            "状态",
            "耗时(ms)",
            "已执行步骤数",
            "总请求数",
            "失败请求数",
            "最慢步骤",
            "Warm打开菜单(ms)",
            "Warm差值(ms)",
        )
    )
    run_id = _dict(result.get("run")).get("id")
    for suite_report, case_report in _case_reports(result):
        suite_code = _suite_code(suite_report, case_report)
        case_code = _case_code(case_report)
        performance = _dict(case_report.get("performance"))
        events = _network_events_for_case(case_report)
        warm = _dict(performance.get("warm_open_menu"))
        sheet.append(
            (
                run_id,
                suite_code,
                case_code,
                _status_label(case_report),
                _int(case_report.get("duration_ms")),
                len(_step_results(case_report)),
                len(events),
                sum(1 for event in events if _is_failed_request(event)),
                _slowest_step_label(case_report),
                _int(warm.get("duration_ms")),
                _optional_int(warm.get("delta_ms")),
            )
        )


def _write_step_overview(sheet, result: dict[str, Any], network_events: list[dict[str, Any]]) -> None:
    sheet.append(
        (
            "运行ID",
            "测试集",
            "用例",
            "步骤序号",
            "触发操作",
            "状态",
            "消息",
            "自动化步骤总耗时(ms)",
            "菜单业务稳定耗时(ms)",
            "完成信号等待(ms)",
            "动作处理耗时(ms)",
            "完成信号",
            "兼容兜底",
            "最慢API请求(ms)",
            "页面标题",
            "页面URL",
            "总请求数",
            "失败请求数",
            "API请求数",
            "静态资源数",
            "上传KB",
            "下载KB",
            "JS堆已用(MB)",
            "最慢请求",
        )
    )
    run_id = _dict(result.get("run")).get("id")
    events_by_step = _events_by_step(network_events)
    for suite_report, case_report in _case_reports(result):
        suite_code = _suite_code(suite_report, case_report)
        case_code = _case_code(case_report)
        for index, step in enumerate(_step_results(case_report), start=1):
            data = _dict(step.get("data"))
            performance = _dict(data.get("performance"))
            network = _dict(performance.get("network"))
            step_events = events_by_step.get((suite_code, case_code, index), [])
            page_state = _dict(data.get("page_state"))
            if not page_state:
                page_state = _dict(_dict(_dict(case_report.get("report")).get("page_state")))
            request_count = _network_count(network, "request_count", step_events)
            failed_count = _network_count(network, "failed_count", [item for item in step_events if _is_failed_request(item)])
            api_count = _network_count(network, "api_request_count", [item for item in step_events if item.get("category") != "static"])
            static_count = _network_count(network, "static_resource_count", [item for item in step_events if item.get("category") == "static"])
            memory = _dict(performance.get("memory"))
            total_ms = _int(performance.get("duration_ms"))
            menu_business_stable_ms = _int(
                performance.get("menu_business_stable_ms")
                or _dict(data.get("timing")).get("menu_business_stable_ms")
            )
            wait_ms = _int(data.get("wait_duration_ms"))
            slowest_api_ms = max(
                (_int(item.get("duration_ms")) for item in step_events if item.get("category") != "static"),
                default=0,
            )
            sheet.append(
                (
                    run_id,
                    suite_code,
                    case_code,
                    index,
                    step.get("action"),
                    "通过" if step.get("success") else "失败",
                    step.get("message"),
                    total_ms,
                    menu_business_stable_ms,
                    wait_ms,
                    max(total_ms - wait_ms, 0),
                    data.get("completion_signal"),
                    bool(data.get("fallback_used")),
                    slowest_api_ms,
                    page_state.get("title"),
                    page_state.get("url"),
                    request_count,
                    failed_count,
                    api_count,
                    static_count,
                    _step_upload_kb(network, step_events),
                    round(sum(_int(item.get("encoded_body_size")) for item in step_events) / 1024, 2),
                    _step_memory_mb(memory),
                    _slow_request_url(step_events),
                )
            )


def _write_network_details(sheet, network_events: list[dict[str, Any]]) -> None:
    sheet.append(_network_header())
    for event in network_events:
        sheet.append(_network_row(event))


def _write_failed_requests(sheet, network_events: list[dict[str, Any]]) -> None:
    sheet.append(_network_header())
    for event in network_events:
        if _is_failed_request(event):
            sheet.append(_network_row(event))


def _write_duplicate_urls(sheet, network_events: list[dict[str, Any]]) -> None:
    sheet.append(("运行ID", "测试集", "用例", "步骤序号", "触发操作", "URL", "调用次数"))
    counter: Counter[tuple[Any, ...]] = Counter(
        (
            event.get("run_id"),
            event.get("suite_code"),
            event.get("case_code"),
            event.get("step_index"),
            event.get("action"),
            event.get("url"),
        )
        for event in network_events
        if event.get("url")
    )
    for key, count in counter.items():
        if count > 1:
            sheet.append((*key, count))
    if sheet.max_row == 1:
        sheet.append(("（无重复调用）", "", "", "", "", "", 0))


def _write_web_vitals(sheet, result: dict[str, Any]) -> None:
    sheet.append(("状态", "运行ID", "测试集", "用例", "步骤序号", "页面URL", "LCP(s)", "LCP评级", "CLS", "CLS评级", "INP(s)", "INP评级"))
    run_id = _dict(result.get("run")).get("id")
    rows = []
    for suite_report, case_report in _case_reports(result):
        suite_code = _suite_code(suite_report, case_report)
        case_code = _case_code(case_report)
        for index, step in enumerate(_step_results(case_report), start=1):
            vitals = _dict(_dict(_dict(step.get("data")).get("performance")).get("web_vitals"))
            if vitals:
                rows.append(
                    (
                        "available",
                        run_id,
                        suite_code,
                        case_code,
                        index,
                        _dict(_dict(step.get("data")).get("page_state")).get("url"),
                        vitals.get("lcp_s"),
                        vitals.get("lcp_rating"),
                        vitals.get("cls"),
                        vitals.get("cls_rating"),
                        vitals.get("inp_s"),
                        vitals.get("inp_rating"),
                    )
                )
    if rows:
        for row in rows:
            sheet.append(row)
    else:
        sheet.append(("unavailable", run_id, "", "", "", "", "", "", "", "", "", ""))


def _write_bpr_recordings(sheet, result: dict[str, Any]) -> None:
    sheet.append(
        (
            "运行ID",
            "测试集",
            "用例",
            "BPR序号",
            "BPR名称",
            "BPR ID",
            "开始控制步骤",
            "结束控制步骤",
            "业务开始步骤",
            "业务结束步骤",
            "业务步骤范围",
            "包含步骤",
            "BPR在线报告链接",
            "开始时间",
            "结束时间",
            "开始时间戳(ms)",
            "结束时间戳(ms)",
            "耗时(ms)",
            "状态",
            "错误信息",
            "本地BPR文件",
            "下载状态",
            "下载错误",
            "概要状态",
            "概要错误",
            *(label for _field, label in SERVER_SUMMARY_FIELDS),
        )
    )
    run_id = _dict(result.get("run")).get("id")
    wrote = False
    for suite_report, case_report in _case_reports(result):
        suite_code = _suite_code(suite_report, case_report)
        case_code = _case_code(case_report)
        sessions = _bpr_sessions(case_report)
        for session in sessions:
            wrote = True
            start_ts = session.get("start_ts") if session.get("start_ts") is not None else session.get("start_time")
            end_ts = session.get("end_ts") if session.get("end_ts") is not None else session.get("end_time")
            summary = _dict(session.get("server_summary"))
            sheet.append(
                (
                    run_id,
                    suite_code,
                    case_code,
                    session.get("index"),
                    session.get("name"),
                    session.get("bpr_id"),
                    session.get("start_control_step"),
                    session.get("end_control_step"),
                    session.get("start_step"),
                    session.get("end_step"),
                    session.get("range"),
                    _bpr_actions_text(session),
                    session.get("report_url"),
                    _format_epoch_ms(start_ts),
                    _format_epoch_ms(end_ts),
                    _optional_int(start_ts),
                    _optional_int(end_ts),
                    _optional_int(session.get("duration_ms")),
                    "通过" if session.get("success") else str(session.get("status") or "失败"),
                    session.get("error"),
                    session.get("report_file"),
                    session.get("download_status"),
                    session.get("download_error"),
                    session.get("summary_status"),
                    session.get("summary_error"),
                    *(summary.get(field) for field, _label in SERVER_SUMMARY_FIELDS),
                )
            )
            _force_row_strings(sheet, sheet.max_row)
    if not wrote:
        sheet.append((run_id, "（无BPR录制）", *("" for _ in range(sheet.max_column - 2))))
        _force_row_strings(sheet, sheet.max_row)


def _network_header() -> tuple[str, ...]:
    return (
        "运行ID",
        "测试集",
        "用例",
        "开始步骤序号",
        "开始操作",
        "完成步骤序号",
        "完成操作",
        "URL",
        "方法",
        "资源类型",
        "分类",
        "状态码",
        "耗时(ms)",
        "Encoded大小(bytes)",
        "失败",
        "错误",
        "步骤上下文",
        "完成步骤上下文",
    )


def _network_row(event: dict[str, Any]) -> tuple[Any, ...]:
    return (
        event.get("run_id"),
        event.get("suite_code"),
        event.get("case_code"),
        event.get("step_index"),
        event.get("action"),
        event.get("completed_step_index"),
        event.get("completed_action"),
        event.get("url"),
        event.get("method"),
        event.get("resource_type"),
        event.get("category"),
        _int(event.get("status")),
        _int(event.get("duration_ms")),
        _int(event.get("encoded_body_size")),
        bool(event.get("failed")),
        event.get("error"),
        event.get("step_context"),
        event.get("completed_step_context"),
    )


def _all_network_events(result: dict[str, Any]) -> list[dict[str, Any]]:
    run_id = _dict(result.get("run")).get("id")
    events: list[dict[str, Any]] = []
    for suite_report, case_report in _case_reports(result):
        suite_code = _suite_code(suite_report, case_report)
        case_code = _case_code(case_report)
        for event in _network_events_for_case(case_report):
            payload = dict(event)
            if not payload.get("run_id"):
                payload["run_id"] = run_id
            if not payload.get("suite_code"):
                payload["suite_code"] = suite_code
            if not payload.get("case_code"):
                payload["case_code"] = case_code
            if payload.get("action") is None:
                payload["action"] = ""
            if not payload.get("step_context"):
                payload["step_context"] = "step" if payload.get("step_index") else "unknown"
            events.append(payload)
    return events


def _network_events_for_case(case_report: dict[str, Any]) -> list[dict[str, Any]]:
    performance = _dict(case_report.get("performance"))
    direct = performance.get("network_events")
    if isinstance(direct, list):
        return [_dict(item) for item in direct if isinstance(item, dict)]
    events: list[dict[str, Any]] = []
    for index, step in enumerate(_step_results(case_report), start=1):
        network = _dict(_dict(_dict(step.get("data")).get("performance")).get("network"))
        for item in network.get("requests") or []:
            if not isinstance(item, dict):
                continue
            payload = dict(item)
            payload.setdefault("step_index", index)
            payload.setdefault("action", step.get("action"))
            events.append(payload)
    return events


def _case_reports(result: dict[str, Any]):
    for suite_report in result.get("suite_reports", []) or []:
        if not isinstance(suite_report, dict):
            continue
        for case_report in suite_report.get("case_reports", []) or []:
            if isinstance(case_report, dict):
                yield suite_report, case_report


def _step_results(case_report: dict[str, Any]) -> list[dict[str, Any]]:
    report = _dict(case_report.get("report"))
    return [_dict(item) for item in report.get("step_results", []) or [] if isinstance(item, dict)]


def _bpr_sessions(case_report: dict[str, Any]) -> list[dict[str, Any]]:
    direct = case_report.get("bpr_sessions")
    if isinstance(direct, list):
        return [_dict(item) for item in direct if isinstance(item, dict)]
    report = _dict(case_report.get("report"))
    nested = report.get("bpr_sessions")
    if isinstance(nested, list):
        return [_dict(item) for item in nested if isinstance(item, dict)]
    return []


def _bpr_actions_text(session: dict[str, Any]) -> str:
    labels = []
    for item in session.get("actions") or []:
        action = _dict(item)
        labels.append(f"#{action.get('step_index')} {action.get('action')}")
    return "，".join(labels)


def _events_by_step(network_events: list[dict[str, Any]]) -> dict[tuple[str, str, int], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for event in network_events:
        key = (
            str(event.get("suite_code") or ""),
            str(event.get("case_code") or ""),
            _int(event.get("step_index")),
        )
        grouped[key].append(event)
    return grouped


def _format_sheet(sheet) -> None:
    header_fill = PatternFill("solid", fgColor="D9EAF7")
    header_font = Font(bold=True)
    for cell in sheet[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    sheet.freeze_panes = "A2"
    if sheet.max_column:
        sheet.auto_filter.ref = sheet.dimensions
    for column_cells in sheet.columns:
        values = [str(cell.value) if cell.value is not None else "" for cell in column_cells]
        width = min(max(len(value) for value in values) + 2, 60)
        sheet.column_dimensions[column_cells[0].column_letter].width = max(width, 10)


def _force_row_strings(sheet, row: int) -> None:
    for cell in sheet[row]:
        if isinstance(cell.value, str):
            cell.data_type = "s"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _step_upload_kb(network: dict[str, Any], events: list[dict[str, Any]]) -> float | None:
    if "request_body_size_available" in network:
        if not network.get("request_body_size_available"):
            return None
        size = _optional_int(network.get("request_body_size"))
    elif events and all(event.get("request_body_size_available") is True for event in events):
        sizes = [_optional_int(event.get("request_body_size")) for event in events]
        size = sum(sizes) if all(item is not None for item in sizes) else None
    else:
        return None
    return round(size / 1024, 2) if size is not None else None


def _step_memory_mb(memory: dict[str, Any]) -> float | None:
    if memory.get("available") is not True:
        return None
    size = _optional_int(memory.get("used_js_heap_size"))
    return round(size / 1024 / 1024, 2) if size is not None else None


def _format_epoch_ms(value: Any) -> str:
    milliseconds = _optional_int(value)
    if milliseconds is None:
        return ""
    local = datetime.fromtimestamp(milliseconds / 1000).astimezone()
    offset = local.strftime("%z")
    return (
        local.strftime("%Y-%m-%d %H:%M:%S.")
        + f"{milliseconds % 1000:03d} "
        + offset[:3]
        + ":"
        + offset[3:]
    )


def _suite_code(suite_report: dict[str, Any], case_report: dict[str, Any]) -> str:
    return str(case_report.get("suite_code") or _dict(suite_report.get("suite")).get("code") or "")


def _case_code(case_report: dict[str, Any]) -> str:
    return str(_dict(case_report.get("case")).get("code") or "")


def _status_label(case_report: dict[str, Any]) -> str:
    status = str(case_report.get("status") or "")
    return {"passed": "通过", "failed": "失败", "skipped": "跳过"}.get(status, status or ("通过" if case_report.get("success") else "失败"))


def _network_count(network: dict[str, Any], key: str, fallback_events: list[dict[str, Any]]) -> int:
    if key in network:
        return _int(network.get(key))
    return len(fallback_events)


def _is_failed_request(event: dict[str, Any]) -> bool:
    status = _int(event.get("status"))
    return bool(event.get("failed")) or status >= 400


def _slow_request_url(events: list[dict[str, Any]]) -> str:
    if not events:
        return ""
    event = max(events, key=lambda item: _int(item.get("duration_ms")))
    return str(event.get("url") or "")


def _slowest_step_label(case_report: dict[str, Any]) -> str:
    slowest = None
    for index, step in enumerate(_step_results(case_report), start=1):
        duration = _int(_dict(_dict(step.get("data")).get("performance")).get("duration_ms"))
        if slowest is None or duration > slowest[0]:
            slowest = (duration, index, step.get("action"))
    if slowest is None:
        return ""
    return f"#{slowest[1]} {slowest[2]} {slowest[0]}ms"


def _slow_label(value: Any) -> str:
    item = _dict(value)
    if not item:
        return ""
    parts = [str(item.get("suite_code") or ""), str(item.get("case_code") or ""), str(item.get("action") or "")]
    label = " / ".join(part for part in parts if part)
    duration = _int(item.get("duration_ms"))
    return f"{label} {duration}ms".strip()
