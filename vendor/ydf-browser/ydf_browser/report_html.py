from __future__ import annotations

import json
import os
from html import escape
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

from .bpr_report import _report_origin


def render_html_report(result: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_document(result, output_path), encoding="utf-8")
    return output_path


def _render_document(result: dict[str, Any], output_path: Path) -> str:
    run = _dict(result.get("run"))
    totals = _dict(result.get("totals"))
    suite_reports = [_dict(item) for item in _list(result.get("suite_reports"))]
    cases = _flatten_cases(suite_reports)
    failures = [item for item in cases if item["status"] in {"failed", "skipped"}]
    pass_rate = _pass_rate(totals)
    status_class = "status-pass" if result.get("success") else "status-fail"
    status_text = "通过" if result.get("success") else "未通过"
    report_href = _path_href(result.get("report_file"), output_path)
    events_href = _path_href(result.get("events_file"), output_path)
    performance_href = _path_href(result.get("performance_file"), output_path)
    profile = _dict(run.get("profile"))
    optional_bpr_styles = _optional_bpr_styles(result)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>YDF Browser 测试报告 - {_e(run.get("id") or "report")}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7fb;
      --panel: #ffffff;
      --text: #172033;
      --muted: #64748b;
      --line: #dbe3ef;
      --pass: #16885a;
      --pass-bg: #e7f7ef;
      --fail: #c93535;
      --fail-bg: #fff0f0;
      --skip: #9a6a10;
      --skip-bg: #fff6db;
      --info: #2563a8;
      --info-bg: #eef6ff;
      --shadow: 0 16px 40px rgba(23, 32, 51, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.5;
    }}
    header {{
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      position: sticky;
      top: 0;
      z-index: 5;
    }}
    .header-inner, main {{
      width: min(1280px, calc(100vw - 40px));
      margin: 0 auto;
    }}
    .header-inner {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
      min-height: 72px;
    }}
    h1, h2, h3, p {{ margin-top: 0; }}
    h1 {{ font-size: 22px; margin-bottom: 2px; }}
    h2 {{ font-size: 18px; margin-bottom: 16px; }}
    h3 {{ font-size: 15px; margin-bottom: 10px; }}
    a {{ color: var(--info); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    main {{ padding: 24px 0 48px; }}
    .muted {{ color: var(--muted); }}
    .status-pill, .pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }}
    .status-pass {{ color: var(--pass); background: var(--pass-bg); }}
    .status-fail {{ color: var(--fail); background: var(--fail-bg); }}
    .status-skipped {{ color: var(--skip); background: var(--skip-bg); }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 18px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    .metric {{ padding: 18px; }}
    .metric-label {{ color: var(--muted); font-size: 12px; margin-bottom: 8px; }}
    .metric-value {{ font-size: 28px; font-weight: 760; letter-spacing: 0; }}
    .metric-sub {{ color: var(--muted); font-size: 12px; margin-top: 4px; }}
    .section {{ padding: 18px; margin-top: 18px; }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px 18px;
      margin-top: 12px;
      color: var(--muted);
      font-size: 13px;
    }}
    .meta b {{ display: block; color: var(--text); font-size: 13px; font-weight: 650; overflow-wrap: anywhere; }}
    .toolbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
      flex-wrap: wrap;
    }}
    .search {{
      width: min(420px, 100%);
      padding: 9px 11px;
      border: 1px solid var(--line);
      border-radius: 6px;
      font-size: 14px;
      background: #fff;
    }}
    .filters {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .filters button {{
      border: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      border-radius: 6px;
      padding: 8px 11px;
      cursor: pointer;
    }}
    .filters button.active {{ border-color: var(--info); background: var(--info-bg); color: var(--info); }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px 8px; border-top: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 12px; font-weight: 700; background: #fafbfd; }}
    td {{ font-size: 13px; }}
    .case-table {{ table-layout: fixed; }}
    .case-summary {{ display: grid; grid-template-columns: 34% 90px 110px minmax(0, 1fr); gap: 0; }}
    .case-summary > * {{ min-width: 0; padding-right: 16px; overflow-wrap: anywhere; }}
    .case-summary .case-title::before {{ content: "▸ "; color: var(--muted); }}
    details[open] > .case-summary .case-title::before {{ content: "▾ "; }}
    .case-title {{ font-weight: 700; }}
    .case-code {{ color: var(--muted); font-size: 12px; margin-top: 2px; overflow-wrap: anywhere; }}
    details {{ border-top: 1px solid var(--line); }}
    details:first-child {{ border-top: 0; }}
    summary {{ cursor: pointer; padding: 12px 0; list-style: none; }}
    summary::-webkit-details-marker {{ display: none; }}
    .failure-list {{ display: grid; gap: 10px; }}
    .failure-card {{
      border: 1px solid var(--line);
      border-left: 4px solid var(--fail);
      border-radius: 7px;
      padding: 12px;
      background: #fff;
    }}
    .failure-card.skipped {{ border-left-color: var(--skip); }}
    .failure-top {{ display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }}
    .error-text {{
      margin: 8px 0 0;
      color: #701f1f;
      background: var(--fail-bg);
      border-radius: 6px;
      padding: 9px 10px;
      overflow-wrap: anywhere;
    }}
    .steps {{ margin-top: 10px; }}
    .step {{
      display: grid;
      grid-template-columns: 90px 170px minmax(0, 1fr);
      gap: 10px;
      padding: 9px 0;
      border-top: 1px solid var(--line);
      font-size: 13px;
    }}
    .step:first-child {{ border-top: 0; }}
    .step > * {{ min-width: 0; overflow-wrap: anywhere; }}
    .step-message {{ overflow-wrap: anywhere; }}
    .debug {{
      margin-top: 8px;
      display: grid;
      gap: 8px;
    }}
    pre {{
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      background: #101828;
      color: #eef4ff;
      border-radius: 6px;
      padding: 10px;
      font-size: 12px;
      margin: 0;
    }}
    .artifact-list {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 8px; }}
    .artifact {{
      width: 180px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      padding: 8px;
    }}
    .artifact img {{ display: block; width: 100%; max-height: 120px; object-fit: contain; border-radius: 5px; background: #f8fafc; }}
    .artifact a {{ display: block; margin-top: 6px; font-size: 12px; overflow-wrap: anywhere; }}
    body.preview-open {{ overflow: hidden; }}
    #screenshotPreview {{ width: 96vw; max-width: none; height: 94vh; max-height: none; padding: 0; border: 0; background: transparent; color: var(--text); overflow: hidden; }}
    #screenshotPreview::backdrop {{ background: rgba(15, 23, 42, .8); }}
    .preview-toolbar {{ display: flex; align-items: center; gap: 12px; padding: 10px; background: var(--panel); border-radius: 6px; }}
    #previewTitle {{ flex: 1; min-width: 0; overflow-wrap: anywhere; }}
    .preview-toolbar button {{ flex-shrink: 0; cursor: pointer; padding: 8px 12px; }}
    .preview-stage {{ flex: 1; min-height: 0; overflow: auto; display: flex; }}
    .preview-stage img {{ display: block; margin: auto; max-width: 100%; max-height: 100%; object-fit: contain; }}
    .preview-stage.original img {{ max-width: none; max-height: none; flex-shrink: 0; }}
    #screenshotPreview[open] {{ display: flex; flex-direction: column; gap: 12px; }}
    .perf-list {{ display: grid; gap: 8px; margin: 10px 0 0; }}
    .perf-item {{ font-size: 13px; color: var(--muted); overflow-wrap: anywhere; }}
    .perf-line {{ display: block; margin-top: 4px; color: var(--muted); font-size: 12px; }}
    {optional_bpr_styles}
    .empty {{
      border: 1px dashed var(--line);
      border-radius: 8px;
      padding: 28px;
      text-align: center;
      color: var(--muted);
      background: #fff;
    }}
    .hidden {{ display: none !important; }}
    @media (max-width: 900px) {{
      .header-inner, main {{ width: min(100vw - 24px, 1280px); }}
      .grid, .meta {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .step {{ grid-template-columns: 1fr; }}
      .case-table thead {{ display: none; }}
      .case-summary {{ grid-template-columns: minmax(0, 1fr) auto auto; gap: 8px; }}
      .case-result {{ grid-column: 1 / -1; }}
    }}
    @media (max-width: 560px) {{
      .grid, .meta {{ grid-template-columns: 1fr; }}
      .header-inner {{ align-items: flex-start; flex-direction: column; padding: 14px 0; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <div>
        <h1>YDF Browser 测试报告</h1>
        <div class="muted">Run {_e(run.get("id") or "-")}</div>
      </div>
      <span class="status-pill {status_class}">{status_text}</span>
    </div>
  </header>
  <main>
    <section aria-labelledby="overview-title">
      <h2 id="overview-title">验收总览</h2>
      <div class="grid">
        {_metric("通过率", f"{pass_rate:.1f}%", f"{_n(totals.get('passed'))}/{_n(totals.get('cases'))} cases")}
        {_metric("通过", _n(totals.get("passed")), "passed")}
        {_metric("失败", _n(totals.get("failed")), "failed")}
        {_metric("跳过", _n(totals.get("skipped")), "skipped")}
      </div>
      <div class="panel section">
        <h3>运行信息</h3>
        <div class="meta">
          {_meta("开始时间", run.get("started_at"))}
          {_meta("结束时间", run.get("ended_at"))}
          {_meta("耗时", _format_duration(run.get("duration_ms")))}
          {_meta("并发", run.get("concurrency"))}
          {_meta("环境", run.get("env"))}
          {_meta("Headless", run.get("headless"))}
          {_meta("Profile 模式", profile.get("mode"))}
          {_meta("Profile 路径", profile.get("path"))}
          {_meta("Cookies reset", profile.get("cookies_reset"))}
          {_meta("Git", _git_label(_dict(run.get("git"))))}
          {_meta("输入", ", ".join(str(item) for item in _list(run.get("dsl_inputs"))) or "-")}
        </div>
        <p class="muted" style="margin:14px 0 0">
          原始数据：
          {_link("report.json", report_href)}
          {(" / " + _link("events.jsonl", events_href)) if events_href else ""}
          {(" / " + _link("performance.xlsx", performance_href)) if performance_href else ""}
        </p>
      </div>
    </section>
    {_render_performance_overview(run, cases, performance_href)}
    <section class="panel section" aria-labelledby="failure-title">
      <h2 id="failure-title">失败与跳过摘要</h2>
      {_render_failure_summary(failures, output_path)}
    </section>
    <section class="panel section" aria-labelledby="suite-title">
      <div class="toolbar">
        <h2 id="suite-title" style="margin-bottom:0">套件与用例</h2>
        <input id="caseSearch" class="search" type="search" placeholder="搜索 suite / case / 错误 / action">
        <div class="filters" aria-label="状态筛选">
          <button class="active" type="button" data-filter="all">全部</button>
          <button type="button" data-filter="failed">失败</button>
          <button type="button" data-filter="skipped">跳过</button>
          <button type="button" data-filter="passed">通过</button>
        </div>
      </div>
      {_render_suites(suite_reports, output_path)}
    </section>
  </main>
  <dialog id="screenshotPreview" aria-labelledby="previewTitle">
    <div class="preview-toolbar">
      <strong id="previewTitle">截图预览</strong>
      <button type="button" id="previewSize" aria-pressed="false">原始尺寸</button>
      <button type="button" id="previewClose" autofocus aria-label="关闭截图">关闭 ×</button>
    </div>
    <div class="preview-stage"><img id="previewImage" alt=""></div>
  </dialog>
  <script>
    const preview = document.getElementById("screenshotPreview");
    const previewImage = document.getElementById("previewImage");
    const previewStage = preview.querySelector(".preview-stage");
    const previewSize = document.getElementById("previewSize");
    document.addEventListener("click", (event) => {{
      const link = event.target.closest("a[data-screenshot]");
      if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      previewImage.src = link.href;
      previewImage.alt = link.dataset.screenshot;
      document.getElementById("previewTitle").textContent = link.dataset.screenshot;
      previewStage.classList.remove("original");
      previewSize.textContent = "原始尺寸";
      previewSize.setAttribute("aria-pressed", "false");
      document.body.classList.add("preview-open");
      preview.showModal();
      previewStage.scrollTo(0, 0);
    }});
    previewSize.addEventListener("click", () => {{
      const original = previewStage.classList.toggle("original");
      previewSize.textContent = original ? "适应窗口" : "原始尺寸";
      previewSize.setAttribute("aria-pressed", String(original));
    }});
    document.getElementById("previewClose").addEventListener("click", () => preview.close());
    preview.addEventListener("click", (event) => {{
      if (event.target === preview || event.target === previewStage) preview.close();
    }});
    preview.addEventListener("close", () => {{
      document.body.classList.remove("preview-open");
      previewImage.removeAttribute("src");
    }});
    const state = {{ filter: "all", query: "" }};
    const buttons = Array.from(document.querySelectorAll("[data-filter]"));
    const search = document.getElementById("caseSearch");
    function applyFilters() {{
      const query = state.query.trim().toLowerCase();
      for (const row of document.querySelectorAll("[data-case-row]")) {{
        const statusMatch = state.filter === "all" || row.dataset.status === state.filter;
        const textMatch = !query || row.dataset.search.includes(query);
        row.classList.toggle("hidden", !(statusMatch && textMatch));
      }}
      for (const suite of document.querySelectorAll("[data-suite]")) {{
        const visibleRows = suite.querySelectorAll("[data-case-row]:not(.hidden)").length;
        suite.classList.toggle("hidden", visibleRows === 0);
      }}
    }}
    buttons.forEach((button) => {{
      button.addEventListener("click", () => {{
        state.filter = button.dataset.filter;
        buttons.forEach((item) => item.classList.toggle("active", item === button));
        applyFilters();
      }});
    }});
    search.addEventListener("input", () => {{
      state.query = search.value;
      applyFilters();
    }});
  </script>
</body>
</html>
"""


def _flatten_cases(suite_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for suite_report in suite_reports:
        suite = _dict(suite_report.get("suite"))
        for case_report in _list(suite_report.get("case_reports")):
            item = _dict(case_report)
            item["_suite"] = suite
            cases.append(item)
    return cases


def _render_failure_summary(failures: list[dict[str, Any]], output_path: Path) -> str:
    if not failures:
        return '<div class="empty">没有失败或跳过用例</div>'
    cards = []
    for case_report in failures:
        status = str(case_report.get("status") or "")
        case = _dict(case_report.get("case"))
        suite = _dict(case_report.get("_suite"))
        first_error = _first_error(case_report)
        failed_step = _first_failed_step(case_report)
        artifacts = _artifacts_from_step(failed_step, output_path)
        status_label = "跳过" if status == "skipped" else "失败"
        status_class = "status-skipped" if status == "skipped" else "status-fail"
        skipped_class = " skipped" if status == "skipped" else ""
        cards.append(
            f"""
            <article class="failure-card{skipped_class}">
              <div class="failure-top">
                <div>
                  <div class="case-title">{_e(case.get("name") or case.get("code") or "-")}</div>
                  <div class="case-code">{_e(suite.get("code") or "-")} / {_e(case.get("code") or "-")}</div>
                </div>
                <span class="pill {status_class}">{status_label}</span>
              </div>
              <p class="error-text">{_e(first_error or case_report.get("skip_reason") or "-")}</p>
              <div class="muted">失败 action：{_e(_dict(failed_step).get("action") or "-")}</div>
              {_render_artifacts(artifacts)}
            </article>
            """
        )
    return f'<div class="failure-list">{"".join(cards)}</div>'


def _render_performance_overview(run: dict[str, Any], cases: list[dict[str, Any]], performance_href: str) -> str:
    performance = _dict(run.get("performance"))
    if not performance.get("enabled"):
        return ""
    export_error = performance.get("export_error")
    summary = _dict(performance.get("summary"))
    cache_modes = ", ".join(str(item) for item in _list(performance.get("cache_modes"))) or "-"
    slowest_case = _dict(summary.get("slowest_case"))
    slowest_step = _dict(summary.get("slowest_step"))
    api_requests = [_dict(item) for item in _list(summary.get("top_slow_api_requests"))][:5]
    static_requests = [_dict(item) for item in _list(summary.get("top_slow_static_resources"))][:5]
    api_html = _render_slow_request_list(api_requests, "暂无慢 AJAX/API 请求")
    static_html = _render_slow_request_list(static_requests, "暂无慢静态资源")
    warm_count = sum(1 for item in cases if _dict(item.get("performance")).get("warm_open_menu"))
    return f"""
    <section class="panel section" aria-labelledby="performance-title">
      <h2 id="performance-title">性能概览</h2>
      <div class="grid">
        {_metric("平均冷启动用例耗时", _format_duration(summary.get("cold_case_avg_ms")), "cold_ephemeral")}
        {_metric("最大冷启动用例耗时", _format_duration(summary.get("cold_case_max_ms")), _slow_case_label(slowest_case))}
        {_metric("Warm 打开菜单", _format_duration(summary.get("warm_open_menu_avg_ms")), f"{warm_count} cases · warm_same_context_open_menu")}
        {_metric("网络失败", _n(summary.get("network_failed_count")), "failed requests")}
      </div>
      <div class="meta">
        {_meta("缓存模式", cache_modes)}
        {_meta("最慢用例", _slow_case_label(slowest_case))}
        {_meta("最慢步骤", _slow_step_label(slowest_step))}
        {_meta("慢 AJAX/API Top 5", f"{len(api_requests)} 条")}
        {_meta("慢静态资源 Top 5", f"{len(static_requests)} 条")}
        {_meta("Excel 性能文件", "performance.xlsx" if performance_href else "-")}
        {_meta("Excel 导出错误", export_error or "-")}
      </div>
      <div class="perf-list">
        <div class="case-title">慢 AJAX/API Top 5</div>
        {api_html}
        <div class="case-title" style="margin-top:8px">慢静态资源 Top 5</div>
        {static_html}
      </div>
    </section>
    """


def _render_slow_request_list(requests: list[dict[str, Any]], empty_text: str) -> str:
    if not requests:
        return f'<div class="perf-item">{_e(empty_text)}</div>'
    return "".join(
        f'<div class="perf-item">{_e(item.get("case_code") or "-")} / {_e(item.get("action") or "-")} · '
        f'{_e(_format_duration(item.get("duration_ms")))} · {_e(_request_path(item.get("url")))}</div>'
        for item in requests
    )


def _render_suites(suite_reports: list[dict[str, Any]], output_path: Path) -> str:
    if not suite_reports:
        return '<div class="empty">暂无用例</div>'
    sections = []
    for suite_report in suite_reports:
        suite = _dict(suite_report.get("suite"))
        totals = _dict(suite_report.get("totals"))
        rows = [_render_case_row(_dict(item), suite, output_path) for item in _list(suite_report.get("case_reports"))]
        sections.append(
            f"""
            <details data-suite open>
              <summary>
                <div class="failure-top">
                  <div>
                    <div class="case-title">{_e(suite.get("name") or suite.get("code") or "-")}</div>
                    <div class="case-code">{_e(suite.get("code") or "-")} · {_e(suite_report.get("dsl_file") or "")}</div>
                  </div>
                  <span class="pill {'status-pass' if suite_report.get('success') else 'status-fail'}">
                    {_n(totals.get("passed"))}/{_n(totals.get("cases"))} 通过
                  </span>
                </div>
              </summary>
              <table class="case-table">
                <thead>
                  <tr>
                    <th style="width:34%">用例</th>
                    <th style="width:90px">状态</th>
                    <th style="width:110px">耗时</th>
                    <th>结果</th>
                  </tr>
                </thead>
                <tbody>
                  {"".join(rows)}
                </tbody>
              </table>
            </details>
            """
        )
    return "".join(sections)


def _render_case_row(case_report: dict[str, Any], suite: dict[str, Any], output_path: Path) -> str:
    case = _dict(case_report.get("case"))
    status = str(case_report.get("status") or ("passed" if case_report.get("success") else "failed"))
    first_error = _first_error(case_report)
    failed_step = _first_failed_step(case_report)
    search_text = " ".join(
        str(value or "")
        for value in (
            suite.get("code"),
            suite.get("name"),
            case.get("code"),
            case.get("name"),
            first_error,
            _dict(failed_step).get("action"),
        )
    ).lower()
    detail_html = _render_case_details(case_report, output_path)
    status_label = {"passed": "通过", "failed": "失败", "skipped": "跳过"}.get(status, status)
    status_class = {"passed": "status-pass", "failed": "status-fail", "skipped": "status-skipped"}.get(status, "status-skipped")
    result_text = case_report.get("skip_reason") if status == "skipped" else first_error
    if not result_text:
        result_text = "全部步骤通过"
    return f"""
      <tr data-case-row data-status="{_attr(status)}" data-search="{_attr(search_text)}">
        <td colspan="4">
          <details>
            <summary class="case-summary">
              <div>
              <div class="case-title">{_e(case.get("name") or case.get("code") or "-")}</div>
              <div class="case-code">{_e(case.get("code") or "-")} · {_e(case_report.get("dsl_file") or "")}</div>
              </div>
              <div><span class="pill {status_class}">{_e(status_label)}</span></div>
              <div>{_e(_format_duration(case_report.get("duration_ms")))}</div>
              <div class="case-result">{_e(result_text)}</div>
            </summary>
            {detail_html}
          </details>
        </td>
      </tr>
    """


def _render_case_details(case_report: dict[str, Any], output_path: Path) -> str:
    case = _dict(case_report.get("case"))
    report = _dict(case_report.get("report"))
    steps = [_dict(item) for item in _list(report.get("step_results"))]
    return f"""
      <div class="meta">
        {_meta("用户", case.get("user"))}
        {_meta("默认组织", case.get("default_org"))}
        {_meta("标签", ", ".join(str(item) for item in _list(case.get("tags"))) or "-")}
        {_meta("描述", case.get("description"))}
        {_meta("准备耗时", _format_setup_timing(report))}
      </div>
      <div class="steps">
        {"".join(_render_step(index, step, output_path) for index, step in enumerate(steps, start=1)) or '<div class="empty">暂无步骤明细</div>'}
      </div>
      {_render_bpr_sessions(case_report)}
    """


def _render_step(index: int, step: dict[str, Any], output_path: Path) -> str:
    success = bool(step.get("success"))
    status_class = "status-pass" if success else "status-fail"
    status_text = "通过" if success else "失败"
    timing_line = _render_step_timing(step)
    performance_line = _render_step_performance(step)
    debug = "" if success else _render_step_debug(step, output_path)
    return f"""
      <div class="step">
        <div><span class="pill {status_class}">#{index} {status_text}</span></div>
        <div>{_e(step.get("action") or "-")}</div>
        <div class="step-message">
          {_e(step.get("message") or "")}
          {timing_line}
          {performance_line}
          {debug}
        </div>
      </div>
    """


def _render_step_timing(step: dict[str, Any]) -> str:
    timing = _dict(_dict(step.get("data")).get("timing"))
    if not timing:
        return ""
    duration = _format_duration(timing.get("duration_ms")).replace(" ms", "ms")
    phases = _dict(timing.get("phases"))
    phase_text = " · ".join(
        f"{name} {_format_duration(value).replace(' ms', 'ms')}"
        for name, value in phases.items()
    )
    text = f"步骤耗时 {duration}" + (f" · {phase_text}" if phase_text else "")
    return f'<span class="perf-line">{_e(text)}</span>'


def _format_setup_timing(report: dict[str, Any]) -> str:
    setup = _dict(_dict(report.get("timing")).get("setup"))
    if not setup:
        return "-"
    return " · ".join(
        f"{name} {_format_duration(_dict(data).get('duration_ms')).replace(' ms', 'ms')}"
        for name, data in setup.items()
    )


def _render_step_performance(step: dict[str, Any]) -> str:
    performance = _dict(_dict(step.get("data")).get("performance"))
    if not performance:
        return ""
    network = _dict(performance.get("network"))
    duration = _format_duration(performance.get("duration_ms")).replace(" ms", "ms")
    text = (
        f"{step.get('action') or '-'} · {duration} · "
        f"请求 {_n(network.get('request_count'))} / 失败 {_n(network.get('failed_count'))}"
    )
    return f'<span class="perf-line">{_e(text)}</span>'


def _render_step_debug(step: dict[str, Any], output_path: Path) -> str:
    data = _dict(step.get("data"))
    debug_items = []
    for key in ("error", "notifications", "page_state"):
        if key in data and data[key]:
            debug_items.append(f"<pre>{_e(_json_compact(data[key]))}</pre>")
    artifacts = _artifacts_from_step(step, output_path)
    artifact_html = _render_artifacts(artifacts)
    return f'<div class="debug">{"".join(debug_items)}{artifact_html}</div>' if debug_items or artifact_html else ""


def _render_bpr_sessions(case_report: dict[str, Any]) -> str:
    sessions = _list(case_report.get("bpr_sessions")) or _list(_dict(case_report.get("report")).get("bpr_sessions"))
    if not sessions:
        return ""
    items = []
    for raw in sessions:
        session = _dict(raw)
        report_url = str(session.get("report_url") or "")
        safe_report_url = report_url if _report_origin(report_url) else ""
        report_file_href = _relative_bpr_href(session.get("report_file_href"))
        local_link = (
            f'<a href="{_attr(report_file_href)}" target="_blank" rel="noopener noreferrer">打开本地 BPR 文件</a>'
            if report_file_href
            else "未生成本地 BPR 文件"
        )
        online_link = (
            _link("打开 BPR 在线报告", safe_report_url)
            if safe_report_url
            else "未生成在线报告链接"
        )
        actions = _bpr_actions_text(session)
        status = "通过" if session.get("success") else "失败"
        items.append(
            f"""
            <div class="bpr-item">
              <div class="bpr-title">BPR #{_e(session.get("index") or "-")} · {_e(session.get("name") or "-")} · {_e(status)}</div>
              <div class="bpr-meta">
                范围：{_e(session.get("range") or "-")}；
                控制步骤：{_e(session.get("start_control_step") or "-")} -> {_e(session.get("end_control_step") or "-")}；
                本地报告：{local_link}；在线报告：{online_link}
              </div>
              <div class="bpr-meta">包含步骤：{_e(actions or "-")}</div>
              <div class="bpr-meta">
                下载状态：{_e(session.get("download_status") or "-")}；
                概要状态：{_e(session.get("summary_status") or "-")}
              </div>
              {f'<div class="error-text">{_e(session.get("error"))}</div>' if session.get("error") else ""}
            </div>
            """
        )
    return f'<div class="bpr-list">{"".join(items)}</div>'


def _optional_bpr_styles(result: dict[str, Any]) -> str:
    if not _has_bpr_sessions(result):
        return ""
    return """
    .bpr-list { display: grid; gap: 8px; margin: 12px 0 2px; }
    .bpr-item {
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      padding: 10px;
      font-size: 13px;
    }
    .bpr-title { font-weight: 700; margin-bottom: 4px; }
    .bpr-meta { color: var(--muted); overflow-wrap: anywhere; }
    """


def _has_bpr_sessions(result: dict[str, Any]) -> bool:
    for suite_report in _list(result.get("suite_reports")):
        for case_report in _list(_dict(suite_report).get("case_reports")):
            report = _dict(_dict(case_report).get("report"))
            if _list(_dict(case_report).get("bpr_sessions")) or _list(report.get("bpr_sessions")):
                return True
    return False


def _bpr_actions_text(session: dict[str, Any]) -> str:
    labels = []
    for item in _list(session.get("actions")):
        action = _dict(item)
        labels.append(f"#{action.get('step_index')} {action.get('action')}")
    return "，".join(labels)


def _render_artifacts(artifacts: list[dict[str, str]]) -> str:
    if not artifacts:
        return ""
    items = []
    for artifact in artifacts:
        href = _attr(artifact["href"])
        label = _e(artifact["label"])
        screenshot = f' data-screenshot="{_attr(artifact["label"])}"' if artifact["image"] else ""
        preview = f'<a href="{href}"{screenshot}><img src="{href}" alt="{label}"></a>' if artifact["image"] else ""
        items.append(f'<div class="artifact">{preview}<a href="{href}"{screenshot}>{label}</a></div>')
    return f'<div class="artifact-list">{"".join(items)}</div>'


def _artifacts_from_step(step: dict[str, Any] | None, output_path: Path) -> list[dict[str, Any]]:
    data = _dict(_dict(step).get("data"))
    raw_files = _list(data.get("archived_diagnostic_files")) or _list(data.get("diagnostic_files"))
    artifacts = []
    for raw_file in raw_files:
        href = _path_href(raw_file, output_path)
        if not href:
            continue
        label = Path(str(raw_file)).name or str(raw_file)
        suffix = Path(str(raw_file)).suffix.lower()
        artifacts.append({"href": href, "label": label, "image": suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}})
    return artifacts


def _first_failed_step(case_report: dict[str, Any]) -> dict[str, Any]:
    report = _dict(case_report.get("report"))
    for step in _list(report.get("step_results")):
        step_data = _dict(step)
        if step_data.get("success") is False:
            return step_data
    return {}


def _first_error(case_report: dict[str, Any]) -> str:
    errors = _list(case_report.get("errors")) or _list(_dict(case_report.get("report")).get("errors"))
    if errors:
        return str(errors[0])
    failed_step = _first_failed_step(case_report)
    return str(failed_step.get("message") or "")


def _path_href(raw_path: Any, output_path: Path) -> str:
    if not raw_path:
        return ""
    text = str(raw_path)
    path = Path(text).expanduser()
    try:
        if path.is_absolute():
            absolute = path.resolve(strict=False)
        else:
            absolute = (Path.cwd() / path).resolve(strict=False)
        base = output_path.parent.resolve(strict=False)
        try:
            return Path(os.path.relpath(absolute, base)).as_posix()
        except ValueError:
            return text
    except OSError:
        return text


def _relative_bpr_href(raw_href: Any) -> str:
    href = str(raw_href or "").strip()
    parts = urlsplit(href)
    decoded_path = unquote(parts.path)
    path = PurePosixPath(decoded_path)
    raw_segments = decoded_path.split("/")
    if (
        not href
        or parts.scheme
        or parts.netloc
        or "?" in href
        or "#" in href
        or "\\" in decoded_path
        or path.is_absolute()
        or not raw_segments
        or raw_segments[0] != "artifacts"
        or any(segment in {"", ".", ".."} for segment in raw_segments)
    ):
        return ""
    return href


def _metric(label: str, value: Any, sub: str) -> str:
    return f"""
      <div class="panel metric">
        <div class="metric-label">{_e(label)}</div>
        <div class="metric-value">{_e(value)}</div>
        <div class="metric-sub">{_e(sub)}</div>
      </div>
    """


def _meta(label: str, value: Any) -> str:
    return f"<div><span>{_e(label)}</span><b>{_e(_display(value))}</b></div>"


def _link(label: str, href: str) -> str:
    return f'<a href="{_attr(href)}">{_e(label)}</a>' if href else _e(label)


def _git_label(git: dict[str, Any]) -> str:
    if not git or git.get("available") is False:
        return "不可用"
    commit = str(git.get("commit") or "")
    short_commit = commit[:8] if commit else "-"
    branch = str(git.get("branch") or "detached")
    dirty = "dirty" if git.get("dirty") else "clean"
    return f"{branch} @ {short_commit} ({dirty})"


def _slow_case_label(item: dict[str, Any]) -> str:
    if not item:
        return "-"
    return f"{item.get('suite_code') or '-'} / {item.get('case_code') or '-'} · {_format_duration(item.get('duration_ms'))}"


def _slow_step_label(item: dict[str, Any]) -> str:
    if not item:
        return "-"
    return f"{item.get('case_code') or '-'} / {item.get('action') or '-'} · {_format_duration(item.get('duration_ms'))}"


def _request_path(raw_url: Any) -> str:
    text = str(raw_url or "").strip()
    if not text:
        return "-"
    parts = urlsplit(text)
    if not parts.scheme or not parts.netloc:
        return text
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    if parts.fragment:
        path = f"{path}#{parts.fragment}"
    return path


def _pass_rate(totals: dict[str, Any]) -> float:
    cases = _as_int(totals.get("cases"))
    if cases == 0:
        return 100.0
    return _as_int(totals.get("passed")) * 100 / cases


def _format_duration(raw_ms: Any) -> str:
    ms = _as_int(raw_ms)
    if ms < 1000:
        return f"{ms} ms"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes = int(seconds // 60)
    rest = int(seconds % 60)
    return f"{minutes}m {rest}s"


def _json_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _display(value: Any) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _n(value: Any) -> str:
    return str(_as_int(value))


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _dict(value: Any = None) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _e(value: Any) -> str:
    return escape(_display(value), quote=False)


def _attr(value: Any) -> str:
    return escape(_display(value), quote=True)
