from __future__ import annotations

import re
from pathlib import Path

from openpyxl import load_workbook

from ydf_browser.bpr_report import SERVER_SUMMARY_FIELDS
from ydf_browser.performance_xlsx import export_performance_xlsx


def _sample_performance_result(tmp_path: Path) -> dict:
    report_file = tmp_path / "report.json"
    performance_file = tmp_path / "performance.xlsx"
    return {
        "success": False,
        "report_file": str(report_file),
        "performance_file": str(performance_file),
        "run": {
            "id": "perf-run",
            "started_at": "2026-05-27T10:00:00+08:00",
            "ended_at": "2026-05-27T10:00:08+08:00",
            "duration_ms": 8000,
            "env": "ydf",
            "performance": {
                "enabled": True,
                "cache_modes": ["persistent_profile_case_open_menu", "persistent_profile_same_case_reopen_menu"],
                "summary": {
                    "slowest_case": {"suite_code": "smoke", "case_code": "case-a", "duration_ms": 8000},
                    "slowest_step": {"suite_code": "smoke", "case_code": "case-a", "action": "toolbar.click", "duration_ms": 2500},
                    "network_failed_count": 1,
                },
            },
        },
        "totals": {"suites": 1, "cases": 1, "passed": 0, "failed": 1, "skipped": 0},
        "suite_reports": [
            {
                "suite": {"code": "smoke", "name": "冒烟", "tenant": "财政一体化"},
                "case_reports": [
                    {
                        "suite_code": "smoke",
                        "case": {"code": "case-a", "name": "性能用例", "steps": []},
                        "status": "failed",
                        "success": False,
                        "duration_ms": 8000,
                        "bpr_sessions": [
                            {
                                "index": 1,
                                "name": "保存录制",
                                "bpr_id": "fake-bpr",
                                "start_control_step": 2,
                                "end_control_step": 4,
                                "start_step": 3,
                                "end_step": 3,
                                "range": "step 3",
                                "actions": [{"step_index": 3, "action": "toolbar.click"}],
                                "report_url": "https://example.yonyougov.top/iuap-ymc-server/proxy/server/bpr/open?pk=fake",
                                "report_file": str(tmp_path / "artifacts" / "smoke" / "case-a" / "bpr" / "1-fake-bpr.html"),
                                "report_file_href": "artifacts/smoke/case-a/bpr/1-fake-bpr.html",
                                "start_ts": 1782046212123,
                                "end_ts": 1782046212623,
                                "duration_ms": 500,
                                "success": True,
                                "download_status": "downloaded",
                                "download_error": "",
                                "summary_status": "parsed",
                                "summary_error": "",
                                "server_summary": {
                                    field: str(125 + index)
                                    for index, (field, _label) in enumerate(SERVER_SUMMARY_FIELDS)
                                },
                            }
                        ],
                        "performance": {
                            "cold": {"duration_ms": 8000, "step_count": 2},
                            "warm_open_menu": {"success": True, "duration_ms": 1200, "delta_ms": -300},
                            "network_events": [
                                {
                                    "suite_code": "smoke",
                                    "case_code": "case-a",
                                    "step_index": 1,
                                    "action": "open_menu",
                                    "completed_step_index": 1,
                                    "completed_action": "open_menu",
                                    "completed_step_context": "step",
                                    "url": "https://example.yonyougov.top/yondif-ams-be/api/list",
                                    "method": "GET",
                                    "resource_type": "xhr",
                                    "category": "api",
                                    "status": 200,
                                    "duration_ms": 345,
                                    "encoded_body_size": 2048,
                                    "request_body_size": 0,
                                    "request_body_size_available": True,
                                    "failed": False,
                                },
                                {
                                    "suite_code": "smoke",
                                    "case_code": "case-a",
                                    "step_index": 2,
                                    "action": "toolbar.click",
                                    "url": "https://example.yonyougov.top/yondif-ams-be/api/save",
                                    "method": "POST",
                                    "resource_type": "xhr",
                                    "category": "api",
                                    "status": 500,
                                    "duration_ms": 980,
                                    "encoded_body_size": 128,
                                    "request_body_size": 10,
                                    "request_body_size_available": True,
                                    "failed": False,
                                    "error": "HTTP 500",
                                },
                                {
                                    "suite_code": "smoke",
                                    "case_code": "case-a",
                                    "step_index": 2,
                                    "action": "toolbar.click",
                                    "url": "https://example.yonyougov.top/yondif-ams-be/api/save",
                                    "method": "POST",
                                    "resource_type": "xhr",
                                    "category": "api",
                                    "status": 0,
                                    "duration_ms": 1200,
                                    "encoded_body_size": 0,
                                    "request_body_size": 0,
                                    "request_body_size_available": True,
                                    "failed": True,
                                    "error": "net::ERR_FAILED",
                                },
                            ],
                        },
                        "report": {
                            "step_results": [
                                {
                                    "action": "open_menu",
                                    "success": True,
                                    "message": "菜单已打开",
                                    "data": {
                                        "page_state": {"url": "https://example.yonyougov.top/#/service/demo", "title": "Demo"},
                                        "performance": {
                                            "duration_ms": 1500,
                                            "menu_business_stable_ms": 1200,
                                            "network": {
                                                "request_count": 1,
                                                "failed_count": 0,
                                                "request_body_size": 0,
                                                "request_body_size_available": True,
                                            },
                                            "memory": {
                                                "available": True,
                                                "used_js_heap_size": 5242880,
                                            },
                                        },
                                    },
                                },
                                {
                                    "action": "toolbar.click",
                                    "success": False,
                                    "message": "保存失败",
                                    "data": {
                                        "wait_duration_ms": 1000,
                                        "completion_signal": "compatibility_timeout",
                                        "fallback_used": True,
                                        "performance": {
                                            "duration_ms": 2500,
                                            "network": {
                                                "request_count": 2,
                                                "failed_count": 1,
                                                "request_body_size": 10,
                                                "request_body_size_available": True,
                                            },
                                            "memory": {
                                                "available": True,
                                                "used_js_heap_size": 10485760,
                                            },
                                        },
                                    },
                                },
                            ]
                        },
                        "errors": ["保存失败"],
                    }
                ],
            }
        ],
    }


def _rows(ws):
    return list(ws.iter_rows(values_only=True))


def test_export_performance_xlsx_writes_expected_sheets_and_step_rows(tmp_path: Path) -> None:
    output_path = tmp_path / "performance.xlsx"

    exported = export_performance_xlsx(_sample_performance_result(tmp_path), output_path)

    assert exported == output_path
    workbook = load_workbook(output_path, data_only=True)
    assert workbook.sheetnames == [
        "运行汇总",
        "用例汇总",
        "步骤总览",
        "网络请求明细",
        "失败请求详情",
        "重复调用URL",
        "Web Vitals评级",
        "BPR录制",
    ]
    step_rows = _rows(workbook["步骤总览"])
    assert step_rows[0][7:14] == (
        "自动化步骤总耗时(ms)",
        "菜单业务稳定耗时(ms)",
        "完成信号等待(ms)",
        "动作处理耗时(ms)",
        "完成信号",
        "兼容兜底",
        "最慢API请求(ms)",
    )
    assert any(row[:8] == ("perf-run", "smoke", "case-a", 1, "open_menu", "通过", "菜单已打开", 1500) for row in step_rows)
    assert any(row[:8] == ("perf-run", "smoke", "case-a", 2, "toolbar.click", "失败", "保存失败", 2500) for row in step_rows)
    open_menu_row = next(row for row in step_rows[1:] if row[4] == "open_menu")
    assert open_menu_row[7:14] == (1500, 1200, 0, 1500, None, False, 345)
    toolbar_row = next(row for row in step_rows[1:] if row[4] == "toolbar.click")
    assert toolbar_row[7:14] == (2500, 0, 1000, 1500, "compatibility_timeout", True, 1200)
    assert step_rows[0][20:24] == ("上传KB", "下载KB", "JS堆已用(MB)", "最慢请求")
    assert toolbar_row[20:23] == (0.01, 0.12, 10.0)
    run_rows = _rows(workbook["运行汇总"])
    assert ("缓存模式", "persistent_profile_case_open_menu, persistent_profile_same_case_reopen_menu") in run_rows
    bpr_rows = _rows(workbook["BPR录制"])
    assert bpr_rows[0][13:17] == (
        "开始时间",
        "结束时间",
        "开始时间戳(ms)",
        "结束时间戳(ms)",
    )
    assert bpr_rows[0][:13] == (
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
    )
    assert any(row[:13] == (
        "perf-run",
        "smoke",
        "case-a",
        1,
        "保存录制",
        "fake-bpr",
        2,
        4,
        3,
        3,
        "step 3",
        "#3 toolbar.click",
        "https://example.yonyougov.top/iuap-ymc-server/proxy/server/bpr/open?pk=fake",
    ) for row in bpr_rows)
    bpr_headers = bpr_rows[0]
    bpr_row = bpr_rows[1]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.123 [+-]\d{2}:\d{2}", bpr_row[13])
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.623 [+-]\d{2}:\d{2}", bpr_row[14])
    assert bpr_row[15:17] == (1782046212123, 1782046212623)
    assert bpr_row[bpr_headers.index("本地BPR文件")] == str(
        tmp_path / "artifacts" / "smoke" / "case-a" / "bpr" / "1-fake-bpr.html"
    )
    assert bpr_row[bpr_headers.index("下载状态")] == "downloaded"
    assert bpr_row[bpr_headers.index("概要状态")] == "parsed"
    assert bpr_row[bpr_headers.index("服务端耗时(ms)")] == "125"
    assert bpr_headers[-len(SERVER_SUMMARY_FIELDS):] == tuple(
        label for _field, label in SERVER_SUMMARY_FIELDS
    )


def test_export_performance_xlsx_writes_network_failures_and_duplicates(tmp_path: Path) -> None:
    output_path = tmp_path / "performance.xlsx"

    export_performance_xlsx(_sample_performance_result(tmp_path), output_path)

    workbook = load_workbook(output_path, data_only=True)
    network_rows = _rows(workbook["网络请求明细"])
    failed_rows = _rows(workbook["失败请求详情"])
    duplicate_rows = _rows(workbook["重复调用URL"])
    header = network_rows[0]
    action_index = header.index("开始操作")
    url_index = header.index("URL")
    status_index = header.index("状态码")
    assert any(
        row[action_index] == "toolbar.click" and row[url_index].endswith("/api/save") and row[status_index] == 500
        for row in network_rows[1:]
    )
    list_request = next(row for row in network_rows[1:] if row[url_index].endswith("/api/list"))
    assert list_request[header.index("完成步骤序号")] == 1
    assert list_request[header.index("完成操作")] == "open_menu"
    assert any(row[url_index].endswith("/api/save") and row[status_index] == 500 for row in failed_rows[1:])
    assert any(row[4] == "toolbar.click" and row[5].endswith("/api/save") and row[6] == 2 for row in duplicate_rows[1:])
    assert _rows(workbook["Web Vitals评级"])[1][0] == "unavailable"


def test_export_performance_xlsx_uses_case_context_when_network_events_have_blank_context(tmp_path: Path) -> None:
    output_path = tmp_path / "performance.xlsx"
    result = _sample_performance_result(tmp_path)
    for event in result["suite_reports"][0]["case_reports"][0]["performance"]["network_events"]:
        event["suite_code"] = ""
        event["case_code"] = ""

    export_performance_xlsx(result, output_path)

    workbook = load_workbook(output_path, data_only=True)
    step_rows = _rows(workbook["步骤总览"])
    open_menu_row = next(row for row in step_rows[1:] if row[3] == 1 and row[4] == "open_menu")
    assert open_menu_row[1:5] == ("smoke", "case-a", 1, "open_menu")
    assert open_menu_row[21] == 2

    network_rows = _rows(workbook["网络请求明细"])
    assert any(row[1:5] == ("smoke", "case-a", 1, "open_menu") for row in network_rows[1:])


def test_export_performance_xlsx_groups_step_downloads_by_step_index_when_action_label_differs(tmp_path: Path) -> None:
    output_path = tmp_path / "performance.xlsx"
    result = _sample_performance_result(tmp_path)
    result["suite_reports"][0]["case_reports"][0]["performance"]["network_events"][0]["action"] = "open_menu.runtime"

    export_performance_xlsx(result, output_path)

    workbook = load_workbook(output_path, data_only=True)
    step_rows = _rows(workbook["步骤总览"])
    open_menu_row = next(row for row in step_rows[1:] if row[3] == 1 and row[4] == "open_menu")
    assert open_menu_row[21] == 2


def test_export_performance_xlsx_marks_empty_bpr_sheet(tmp_path: Path) -> None:
    output_path = tmp_path / "performance.xlsx"
    result = _sample_performance_result(tmp_path)
    result["suite_reports"][0]["case_reports"][0].pop("bpr_sessions", None)

    export_performance_xlsx(result, output_path)

    workbook = load_workbook(output_path, data_only=True)
    bpr_rows = _rows(workbook["BPR录制"])
    assert bpr_rows[1][1] == "（无BPR录制）"
    assert len(bpr_rows[1]) == len(bpr_rows[0])


def test_export_performance_xlsx_leaves_unavailable_upload_and_memory_blank(tmp_path: Path) -> None:
    output_path = tmp_path / "performance.xlsx"
    result = _sample_performance_result(tmp_path)
    step = result["suite_reports"][0]["case_reports"][0]["report"]["step_results"][1]
    step["data"]["performance"]["network"].update(
        request_body_size=0,
        request_body_size_available=False,
        request_body_size_unavailable_reason="request_body_size_unavailable",
    )
    step["data"]["performance"]["memory"] = {
        "available": False,
        "used_js_heap_size": 0,
        "unavailable_reason": "unsupported",
    }

    export_performance_xlsx(result, output_path)

    workbook = load_workbook(output_path, data_only=True)
    rows = _rows(workbook["步骤总览"])
    toolbar_row = next(row for row in rows[1:] if row[4] == "toolbar.click")
    assert toolbar_row[20] is None
    assert toolbar_row[22] is None


def test_export_performance_xlsx_writes_bpr_strings_as_text_not_formulas(tmp_path: Path) -> None:
    output_path = tmp_path / "performance.xlsx"
    result = _sample_performance_result(tmp_path)
    formula = '=HYPERLINK("https://attacker.invalid","click")'
    session = result["suite_reports"][0]["case_reports"][0]["bpr_sessions"][0]
    for key in (
        "name",
        "bpr_id",
        "report_url",
        "report_file",
        "download_status",
        "download_error",
        "summary_status",
        "summary_error",
    ):
        session[key] = formula
    session["success"] = False
    session["status"] = formula
    session["error"] = formula
    session["server_summary"] = {
        field: formula for field, _label in SERVER_SUMMARY_FIELDS
    }

    export_performance_xlsx(result, output_path)

    workbook = load_workbook(output_path, data_only=False)
    sheet = workbook["BPR录制"]
    headers = [cell.value for cell in sheet[1]]
    formula_headers = (
        "BPR名称",
        "BPR ID",
        "BPR在线报告链接",
        "状态",
        "错误信息",
        "本地BPR文件",
        "下载状态",
        "下载错误",
        "概要状态",
        "概要错误",
        *(label for _field, label in SERVER_SUMMARY_FIELDS),
    )
    for header in formula_headers:
        cell = sheet.cell(row=2, column=headers.index(header) + 1)
        assert cell.value == formula
        assert cell.data_type == "s"
    assert all(cell.data_type != "f" for cell in sheet[2])
