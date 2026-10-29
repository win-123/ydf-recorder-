from __future__ import annotations

from pathlib import Path

import pytest

from ydf_browser.report_html import render_html_report


def test_render_html_report_builds_acceptance_summary_and_failure_details(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "smoke" / "case-fail" / "shot.png"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"png")
    report_path = tmp_path / "report.json"
    events_path = tmp_path / "events.jsonl"
    output_path = tmp_path / "report.html"
    result = {
        "success": False,
        "run": {
            "id": "run-1",
            "started_at": "2026-05-09T10:00:00+08:00",
            "ended_at": "2026-05-09T10:05:00+08:00",
            "duration_ms": 300000,
            "concurrency": 2,
            "env": "ydf",
            "headless": True,
            "git": {"branch": "develop", "commit": "abc123456789", "dirty": True},
        },
        "totals": {"suites": 1, "cases": 3, "passed": 1, "failed": 1, "skipped": 1},
        "report_file": str(report_path),
        "events_file": str(events_path),
        "suite_reports": [
            {
                "dsl_file": "examples/smoke.yaml",
                "suite": {"code": "smoke", "name": "冒烟 <套件>", "description": "", "tenant": ""},
                "totals": {"cases": 3, "passed": 1, "failed": 1, "skipped": 1},
                "case_reports": [
                    {
                        "dsl_file": "examples/smoke.yaml",
                        "suite_code": "smoke",
                        "case_index": 1,
                        "total_cases": 3,
                        "status": "passed",
                        "success": True,
                        "duration_ms": 1200,
                        "case": {"code": "case-pass", "name": "通过用例", "description": "", "user": "默认用户", "default_org": "049002", "tags": [], "steps": []},
                        "report": {
                            "step_results": [
                                {
                                    "action": "open_menu",
                                    "success": True,
                                    "message": "菜单已打开（承载方式: direct）",
                                    "data": {"menu_hosting": {"mode": "direct"}},
                                }
                            ],
                            "manifest": {"debug": "SECRET_MANIFEST_SHOULD_NOT_RENDER"},
                            "binding": {"debug": "SECRET_BINDING_SHOULD_NOT_RENDER"},
                        },
                        "errors": [],
                    },
                    {
                        "dsl_file": "examples/smoke.yaml",
                        "suite_code": "smoke",
                        "case_index": 2,
                        "total_cases": 3,
                        "status": "failed",
                        "success": False,
                        "duration_ms": 2400,
                        "case": {"code": "case-fail", "name": "失败用例", "description": "验证失败详情", "user": "默认用户", "default_org": "049002", "tags": ["smoke"], "steps": []},
                        "report": {
                            "step_results": [
                                {"action": "open_menu", "success": True, "message": "菜单已打开", "data": {}},
                                {
                                    "action": "toolbar.click",
                                    "success": False,
                                    "message": "未找到 <保存> <script>alert(1)</script>",
                                    "data": {
                                        "error": {"type": "RuntimeError", "message": "未找到 <保存>"},
                                        "notifications": [{"type": "error", "text": "保存失败"}],
                                        "page_state": {"url": "https://example.test/#/service/demo", "title": "Demo"},
                                        "archived_diagnostic_files": [str(artifact)],
                                    },
                                },
                            ],
                            "errors": ["未找到 <保存> <script>alert(1)</script>"],
                        },
                        "errors": ["未找到 <保存> <script>alert(1)</script>"],
                    },
                    {
                        "dsl_file": "examples/smoke.yaml",
                        "suite_code": "smoke",
                        "case_index": 3,
                        "total_cases": 3,
                        "status": "skipped",
                        "success": False,
                        "skip_reason": "suite stopped after failed case: case-fail",
                        "case": {"code": "case-skip", "name": "跳过用例", "description": "", "user": "", "default_org": "", "tags": [], "steps": []},
                        "report": None,
                        "errors": [],
                    },
                ],
            }
        ],
    }

    rendered = render_html_report(result, output_path)

    html = output_path.read_text(encoding="utf-8")
    assert rendered == output_path
    assert "验收总览" in html
    assert "run-1" in html
    assert "冒烟 &lt;套件&gt;" in html
    assert "失败用例" in html
    assert "跳过用例" in html
    assert "未找到 &lt;保存&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "toolbar.click" in html
    assert "artifacts/smoke/case-fail/shot.png" in html
    assert "SECRET_MANIFEST_SHOULD_NOT_RENDER" not in html
    assert "SECRET_BINDING_SHOULD_NOT_RENDER" not in html
    assert "承载方式: direct" in html


def test_render_html_report_handles_empty_report(tmp_path: Path) -> None:
    output_path = tmp_path / "empty.html"
    result = {
        "success": True,
        "run": {"id": "empty-run", "duration_ms": 0, "concurrency": 1},
        "totals": {"suites": 0, "cases": 0, "passed": 0, "failed": 0, "skipped": 0},
        "suite_reports": [],
    }

    render_html_report(result, output_path)

    html = output_path.read_text(encoding="utf-8")
    assert "empty-run" in html
    assert "暂无用例" in html


def test_render_html_report_shows_lightweight_setup_step_and_phase_timing(tmp_path: Path) -> None:
    output_path = tmp_path / "timing.html"
    result = {
        "success": True,
        "run": {"id": "timing-run", "duration_ms": 500, "concurrency": 1},
        "totals": {"suites": 1, "cases": 1, "passed": 1, "failed": 0, "skipped": 0},
        "suite_reports": [
            {
                "dsl_file": "examples/timing.yaml",
                "suite": {"code": "timing", "name": "计时", "description": "", "tenant": ""},
                "totals": {"cases": 1, "passed": 1, "failed": 0, "skipped": 0},
                "case_reports": [
                    {
                        "dsl_file": "examples/timing.yaml",
                        "suite_code": "timing",
                        "case_index": 1,
                        "total_cases": 1,
                        "status": "passed",
                        "success": True,
                        "duration_ms": 500,
                        "case": {"code": "case-a", "name": "用例 A", "description": "", "user": "", "default_org": "", "tags": [], "steps": []},
                        "report": {
                            "timing": {
                                "setup": {
                                    "login": {"duration_ms": 40, "success": True},
                                    "context": {"duration_ms": 20, "success": True},
                                }
                            },
                            "step_results": [
                                {
                                    "action": "open_menu",
                                    "success": True,
                                    "message": "菜单已打开",
                                    "data": {
                                        "timing": {
                                            "duration_ms": 321,
                                            "phases": {
                                                "resolve_menu_ms": 20,
                                                "browser_open_ms": 100,
                                            },
                                        }
                                    },
                                }
                            ],
                        },
                        "errors": [],
                    }
                ],
            }
        ],
    }

    render_html_report(result, output_path)

    html = output_path.read_text(encoding="utf-8")
    assert "准备耗时" in html
    assert "login 40ms" in html
    assert "步骤耗时 321ms" in html
    assert "browser_open_ms 100ms" in html


def test_render_html_report_shows_performance_overview_and_step_metrics(tmp_path: Path) -> None:
    output_path = tmp_path / "perf.html"
    result = {
        "success": True,
        "performance_file": str(tmp_path / "performance.xlsx"),
        "run": {
            "id": "perf-run",
            "duration_ms": 5000,
            "concurrency": 1,
            "profile": {
                "mode": "persistent",
                "path": "/tmp/ydf-profile",
                "cookies_reset": "visible_to_base_url",
            },
            "performance": {
                "enabled": True,
                "cache_modes": ["persistent_profile_case_open_menu", "persistent_profile_same_case_reopen_menu"],
                "summary": {
                    "cold_case_avg_ms": 2000,
                    "cold_case_max_ms": 2000,
                    "slowest_case": {"suite_code": "smoke", "case_code": "case-a", "duration_ms": 2000},
                    "slowest_step": {"case_code": "case-a", "action": "open_menu", "duration_ms": 800},
                    "network_failed_count": 0,
                    "top_slow_requests": [{"url": "https://example.yonyougov.top/api/demo", "duration_ms": 120}],
                    "top_slow_api_requests": [{"url": "https://example.yonyougov.top/api/demo", "duration_ms": 120}],
                    "top_slow_static_resources": [{"url": "https://example.yonyougov.top/static/app.js", "duration_ms": 80}],
                },
            },
        },
        "totals": {"suites": 1, "cases": 1, "passed": 1, "failed": 0, "skipped": 0},
        "suite_reports": [
            {
                "dsl_file": "examples/perf.yaml",
                "suite": {"code": "smoke", "name": "冒烟", "description": "", "tenant": ""},
                "totals": {"cases": 1, "passed": 1, "failed": 0, "skipped": 0},
                "case_reports": [
                    {
                        "dsl_file": "examples/perf.yaml",
                        "suite_code": "smoke",
                        "case_index": 1,
                        "total_cases": 1,
                        "status": "passed",
                        "success": True,
                        "duration_ms": 2000,
                        "case": {"code": "case-a", "name": "性能用例", "description": "", "user": "", "default_org": "", "tags": [], "steps": []},
                        "performance": {
                            "setup": {"login_ms": 100, "browser_start_ms": 200},
                            "cold": {"duration_ms": 2000},
                            "warm_open_menu": {"duration_ms": 500, "cold_open_menu_ms": 800, "delta_ms": -300},
                        },
                        "report": {
                            "step_results": [
                                {
                                    "action": "open_menu",
                                    "success": True,
                                    "message": "菜单已打开",
                                    "data": {
                                        "performance": {
                                            "duration_ms": 800,
                                            "network": {"request_count": 6, "failed_count": 0},
                                        }
                                    },
                                }
                            ]
                        },
                        "errors": [],
                    }
                ],
            }
        ],
    }

    render_html_report(result, output_path)

    html = output_path.read_text(encoding="utf-8")
    assert "性能概览" in html
    assert "persistent_profile_case_open_menu" in html
    assert "persistent_profile_same_case_reopen_menu" in html
    assert "persistent" in html
    assert "/tmp/ydf-profile" in html
    assert "平均冷启动用例耗时" in html
    assert "Warm 打开菜单" in html
    assert "performance.xlsx" in html
    assert "慢 AJAX/API Top 5" in html
    assert "慢静态资源 Top 5" in html
    assert "open_menu · 800ms · 请求 6 / 失败 0" in html
    assert "/api/demo" in html
    assert "/static/app.js" in html
    assert "https://example.yonyougov.top/api/demo" not in html
    assert "https://example.yonyougov.top/static/app.js" not in html


def test_render_html_report_shows_bpr_sessions(tmp_path: Path) -> None:
    output_path = tmp_path / "bpr.html"
    result = {
        "success": True,
        "run": {"id": "bpr-run", "duration_ms": 1000, "concurrency": 1},
        "totals": {"suites": 1, "cases": 1, "passed": 1, "failed": 0, "skipped": 0},
        "suite_reports": [
            {
                "dsl_file": "examples/bpr.yaml",
                "suite": {"code": "smoke", "name": "冒烟", "tenant": ""},
                "totals": {"cases": 1, "passed": 1, "failed": 0, "skipped": 0},
                "success": True,
                "case_reports": [
                    {
                        "dsl_file": "examples/bpr.yaml",
                        "suite_code": "smoke",
                        "case_index": 1,
                        "total_cases": 1,
                        "status": "passed",
                        "success": True,
                        "duration_ms": 1000,
                        "case": {"code": "case-a", "name": "BPR用例", "description": "", "user": "", "default_org": "", "tags": [], "steps": []},
                        "bpr_sessions": [
                            {
                                "index": 1,
                                "name": "修改并取消",
                                "start_control_step": 2,
                                "end_control_step": 5,
                                "range": "step 3 - step 4",
                                "actions": [
                                    {"step_index": 3, "action": "toolbar.click"},
                                    {"step_index": 4, "action": "toolbar.click"},
                                ],
                                "report_url": "https://example.yonyougov.top/iuap-ymc-server/proxy/server/bpr/open?pk=fake",
                                "report_file": "/private/tmp/sensitive-run/artifacts/smoke/case-a/bpr/1-fake.html",
                                "report_file_href": "artifacts/smoke/case-a/bpr/1-fake.html",
                                "download_status": "downloaded",
                                "download_error": "",
                                "summary_status": "parsed",
                                "summary_error": "",
                                "success": True,
                            },
                            {
                                "index": 2,
                                "name": "无链接录制",
                                "range": "-",
                                "actions": [],
                                "report_url": "",
                                "report_file": "",
                                "report_file_href": "",
                                "download_status": "failed",
                                "download_error": "BPR session 缺少 report_url",
                                "summary_status": "not_attempted",
                                "summary_error": "",
                                "success": False,
                            },
                        ],
                        "report": {"step_results": []},
                        "errors": [],
                    }
                ],
            }
        ],
    }

    render_html_report(result, output_path)

    html = output_path.read_text(encoding="utf-8")
    assert "BPR #1" in html
    assert "修改并取消" in html
    assert "step 3 - step 4" in html
    assert 'href="artifacts/smoke/case-a/bpr/1-fake.html" target="_blank" rel="noopener noreferrer"' in html
    assert "打开本地 BPR 文件" in html
    assert "打开 BPR 在线报告" in html
    assert 'href="https://example.yonyougov.top/iuap-ymc-server/proxy/server/bpr/open?pk=fake"' in html
    assert "下载状态：downloaded" in html
    assert "概要状态：parsed" in html
    assert "下载状态：failed" in html
    assert "概要状态：not_attempted" in html
    assert "未生成在线报告链接" in html
    assert "/private/tmp/sensitive-run" not in html
    assert "#3 toolbar.click，#4 toolbar.click" in html


def test_report_browser_full_width_preview_and_local_bpr(tmp_path: Path) -> None:
    from playwright.sync_api import expect, sync_playwright

    artifact = tmp_path / "artifacts" / "shot.png"
    artifact.parent.mkdir()
    local_bpr = artifact.with_name("bpr.html")
    local_bpr.write_text("<!doctype html><title>BPR local</title><p>Local report</p>", encoding="utf-8")
    diagnostic = artifact.with_suffix(".txt")
    diagnostic.write_text("diagnostic", encoding="utf-8")
    step = {"action": "form.fill", "success": False, "message": "长结果" * 120,
            "data": {"diagnostic_files": [str(artifact), str(diagnostic)]}}
    result = {"success": False, "suite_reports": [{
        "suite": {"name": "布局回归"}, "case_reports": [{
            "status": "failed", "case": {"name": "失败用例"},
            "report": {"step_results": [step] * 8},
            "bpr_sessions": [{"report_file_href": "artifacts/bpr.html"}],
        }],
    }]}
    output = render_html_report(result, tmp_path / "report.html")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1800, "height": 1000})
        page.screenshot(path=str(artifact))
        page.set_viewport_size({"width": 1280, "height": 800})
        errors, downloads = [], []
        page.on("pageerror", lambda error: errors.append(error))
        page.context.on("page", lambda popup: popup.on("download", lambda download: downloads.append(download)))
        page.on("download", lambda download: downloads.append(download))
        page.goto(output.as_uri())
        row = page.locator("[data-case-row]")
        row.locator("summary").click()
        steps = row.locator(".steps")
        assert steps.bounding_box()["width"] > row.bounding_box()["width"] * .95
        page.locator('[data-filter="passed"]').click()
        expect(steps).not_to_be_visible()
        page.locator('[data-filter="all"]').click()
        expect(steps).to_be_visible()
        page.locator("#caseSearch").fill("不存在的用例")
        expect(row).not_to_be_visible()
        page.locator("#caseSearch").fill("")
        expect(steps).to_be_visible()

        dialog = page.locator("#screenshotPreview")
        image = page.locator("#previewImage")
        link = row.locator("a[data-screenshot]").first
        link.scroll_into_view_if_needed()
        scroll_y = page.evaluate("window.scrollY")
        link.click()
        expect(dialog).to_be_visible()
        expect(image).to_have_js_property("naturalWidth", 1800)
        assert image.bounding_box()["width"] <= 1280
        page.locator("#previewSize").click()
        assert image.bounding_box()["width"] == 1800
        page.locator("#previewSize").click()
        image.click()
        expect(dialog).to_be_visible()
        page.locator("#previewClose").click()
        expect(dialog).not_to_be_visible()
        expect(link).to_be_focused()
        assert page.evaluate("window.scrollY") == scroll_y
        link.click()
        page.keyboard.press("Escape")
        expect(dialog).not_to_be_visible()
        # The filename in the failure summary uses the same preview as its thumbnail.
        page.locator(".failure-card a[data-screenshot]").nth(1).click()
        page.mouse.click(1, 1)
        expect(dialog).not_to_be_visible()
        assert page.url == output.as_uri()
        assert row.locator('a[href="artifacts/shot.txt"]').first.get_attribute("data-screenshot") is None

        with page.expect_popup() as opened:
            page.get_by_text("打开本地 BPR 文件", exact=True).click()
        popup = opened.value
        popup.wait_for_load_state()
        assert popup.url == local_bpr.as_uri()
        assert popup.title() == "BPR local"
        assert popup.evaluate("window.opener === null")
        assert not downloads
        popup.close()
        for width in (1920, 390):
            page.set_viewport_size({"width": width, "height": 800})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert steps.bounding_box()["width"] > row.bounding_box()["width"] * .9
        assert not errors
        browser.close()


def test_render_html_report_does_not_link_absolute_bpr_file_href(tmp_path: Path) -> None:
    output_path = tmp_path / "bpr.html"
    result = {
        "success": True,
        "run": {"id": "bpr-run", "duration_ms": 0, "concurrency": 1},
        "totals": {"suites": 1, "cases": 1, "passed": 1, "failed": 0, "skipped": 0},
        "suite_reports": [{
            "suite": {"code": "smoke", "name": "冒烟"},
            "case_reports": [{
                "status": "passed",
                "success": True,
                "case": {"code": "case-a", "name": "BPR用例"},
                "bpr_sessions": [{
                    "index": 1,
                    "success": True,
                    "report_file_href": "/private/tmp/sensitive-run/1-fake.html",
                    "download_status": "downloaded",
                    "summary_status": "parsed",
                }],
                "report": {"step_results": []},
            }],
        }],
    }

    render_html_report(result, output_path)

    html = output_path.read_text(encoding="utf-8")
    assert "/private/tmp/sensitive-run" not in html
    assert 'href="/private/tmp/sensitive-run/1-fake.html"' not in html


@pytest.mark.parametrize(
    "report_url",
    [
        "javascript:alert(1)",
        "http://example.yonyougov.top/bpr/open?pk=fake",
        "https://user:password@example.yonyougov.top/bpr/open?pk=fake",
        "//example.yonyougov.top/bpr/open?pk=fake",
        "https://example.yonyougov.top/bpr/open?pk=fake bad",
    ],
)
def test_render_html_report_hides_unsafe_bpr_online_url(tmp_path: Path, report_url: str) -> None:
    output_path = tmp_path / "bpr.html"
    result = {
        "success": True,
        "run": {"id": "bpr-run", "duration_ms": 0, "concurrency": 1},
        "totals": {"suites": 1, "cases": 1, "passed": 1, "failed": 0, "skipped": 0},
        "suite_reports": [{
            "suite": {"code": "smoke", "name": "冒烟"},
            "case_reports": [{
                "status": "passed",
                "success": True,
                "case": {"code": "case-a", "name": "BPR用例"},
                "bpr_sessions": [{
                    "index": 1,
                    "success": False,
                    "report_url": report_url,
                    "download_status": "failed",
                    "download_error": "BPR 下载: ValueError",
                    "summary_status": "not_attempted",
                }],
                "report": {"step_results": []},
            }],
        }],
    }

    render_html_report(result, output_path)

    html = output_path.read_text(encoding="utf-8")
    assert "打开 BPR 在线报告" not in html
    assert "未生成在线报告链接" in html
    assert "下载状态：failed" in html
    assert "概要状态：not_attempted" in html
    assert report_url not in html


def test_render_html_report_rejects_unsafe_bpr_file_href_url_forms(tmp_path: Path) -> None:
    unsafe_hrefs = (
        "artifacts/smoke/%2e%2e/private.html",
        "artifacts/smoke/%2E%2E/private.html",
        r"artifacts\smoke\case-a\1-fake.html",
        "artifacts/smoke%5Ccase-a/1-fake.html",
        "artifacts/smoke/case-a/1-fake.html?download=1",
        "artifacts/smoke/case-a/1-fake.html?",
        "artifacts/smoke/case-a/1-fake.html#source",
        "artifacts/smoke/case-a/1-fake.html#",
        "artifacts/./case-a/1-fake.html",
        "outside/smoke/case-a/1-fake.html",
        "https://example.test/artifacts/smoke/case-a/1-fake.html",
        "//example.test/artifacts/smoke/case-a/1-fake.html",
    )
    for index, href in enumerate(unsafe_hrefs):
        output_path = tmp_path / f"unsafe-{index}.html"
        result = {
            "success": True,
            "run": {"id": "bpr-run", "duration_ms": 0, "concurrency": 1},
            "totals": {"suites": 1, "cases": 1, "passed": 1, "failed": 0, "skipped": 0},
            "suite_reports": [{
                "suite": {"code": "smoke", "name": "冒烟"},
                "case_reports": [{
                    "status": "passed",
                    "success": True,
                    "case": {"code": "case-a", "name": "BPR用例"},
                    "bpr_sessions": [{
                        "index": 1,
                        "success": True,
                        "report_file_href": href,
                        "download_status": "downloaded",
                        "summary_status": "parsed",
                    }],
                    "report": {"step_results": []},
                }],
            }],
        }

        render_html_report(result, output_path)

        html = output_path.read_text(encoding="utf-8")
        assert "打开本地 BPR 文件" not in html
        assert href not in html
