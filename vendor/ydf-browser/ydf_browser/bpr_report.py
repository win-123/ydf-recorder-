from __future__ import annotations

from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .auth import CasAuthenticator
from .runner import _safe_path_part
from .runtime import PlaywrightRuntime


SERVER_SUMMARY_FIELDS: tuple[tuple[str, str], ...] = (
    ("totalCostTime", "服务端耗时(ms)"),
    ("appCostTime", "计算耗时(ms)"),
    ("totalRedisCostTime", "Cache耗时(ms)/次数"),
    ("totalSqlCostTime", "SQL耗时(ms)/次数"),
    ("totalReadrResultTime", "读结果集耗时(ms)/结果集"),
    ("totalThreadNum", "异步任务数"),
    ("totalRpcNum", "RPC次数"),
    ("totalRuleCostTime", "Rule耗时/数量"),
    ("readFromClientTime", "上行网络耗时(ms)"),
    ("writeToClientTime", "下行网络耗时(ms)"),
    ("readFromClient", "上行流量(bytes)"),
    ("readFromServer", "下行流量(bytes)"),
    ("notClosedConnecttion", "未关闭连接数"),
    ("errorSize", "错误日志数"),
)
_SERVER_SUMMARY_KEYS = frozenset(field for field, _label in SERVER_SUMMARY_FIELDS)


class _ServerSummaryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.summary_depth = 0
        self.data_row_found = False
        self.candidate_row_active = False
        self.field: str | None = None
        self.field_depth = 0
        self.hidden_depth = 0
        self.text_parts: list[str] = []
        self.values: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if not self.summary_depth and attributes.get("id") == "summary-posi":
            self.summary_depth = 1
        elif self.summary_depth:
            self.summary_depth += 1

        if not self.summary_depth:
            return
        if tag == "tr" and not self.data_row_found:
            self.candidate_row_active = True
        if self.field is not None:
            self.field_depth += 1
            if tag in {"script", "style"}:
                self.hidden_depth += 1
        elif self.candidate_row_active and tag == "td":
            field = attributes.get("data-field")
            if field in _SERVER_SUMMARY_KEYS:
                self.data_row_found = True
                self.field = field
                self.field_depth = 1
                self.text_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self.field is not None:
            if tag in {"script", "style"}:
                self.hidden_depth -= 1
            self.field_depth -= 1
            if not self.field_depth:
                value = " ".join("".join(self.text_parts).split())
                if value:
                    self.values.setdefault(self.field, value)
                self.field = None
                self.text_parts = []
        if self.candidate_row_active and tag == "tr":
            self.candidate_row_active = False
        if self.summary_depth:
            self.summary_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.field is not None and not self.hidden_depth:
            self.text_parts.append(data)


def extract_server_summary(path: str | Path) -> dict[str, str]:
    parser = _ServerSummaryParser()
    parser.feed(Path(path).read_text(encoding="utf-8"))
    parser.close()
    summary = {field: parser.values[field] for field, _label in SERVER_SUMMARY_FIELDS if field in parser.values}
    if not summary:
        raise ValueError("BPR 文件中未找到服务端概要")
    return summary


def enrich_bpr_reports(
    result: dict[str, Any],
    env: Any,
    report_dir: str | Path,
    *,
    headless: bool,
) -> None:
    sessions: list[tuple[str, str, int, dict[str, Any]]] = []
    for suite_report in result.get("suite_reports", []):
        suite_code = _safe_path_part((suite_report.get("suite") or {}).get("code") or "suite")
        for case_report in suite_report.get("case_reports", []):
            case_code = _safe_path_part((case_report.get("case") or {}).get("code") or "case")
            direct = case_report.get("bpr_sessions")
            nested = (case_report.get("report") or {}).get("bpr_sessions")
            raw_sessions = direct if isinstance(direct, list) and direct else nested
            if not isinstance(raw_sessions, list):
                continue
            for fallback_index, session in enumerate(raw_sessions, start=1):
                if not isinstance(session, dict):
                    continue
                session.update(
                    {
                        "report_file": "",
                        "report_file_href": "",
                        "download_status": "",
                        "download_error": "",
                        "summary_status": "not_attempted",
                        "summary_error": "",
                        "server_summary": {},
                    }
                )
                index = session.get("index")
                if not isinstance(index, int) or isinstance(index, bool) or index < 1:
                    index = fallback_index
                sessions.append((suite_code, case_code, index, session))

    if not sessions:
        return

    eligible: list[tuple[str, str, int, dict[str, Any]]] = []
    report_origin = ""
    for item in sessions:
        session = item[-1]
        report_url = str(session.get("report_url") or "")
        if not report_url.strip():
            session["download_status"] = "failed"
            session["download_error"] = "BPR session 缺少 report_url"
            continue
        origin = _report_origin(report_url)
        if not origin:
            session["download_status"] = "failed"
            session["download_error"] = "BPR report_url 必须是无 userinfo 的绝对 HTTPS URL"
            continue
        if report_origin and origin != report_origin:
            session["download_status"] = "failed"
            session["download_error"] = "BPR report_url origin 与本次运行不一致"
            continue
        report_origin = origin
        eligible.append(item)

    if not eligible:
        return

    credential = getattr(env, "bpr", None) if env is not None else None
    username = str(getattr(credential, "username", "") or "")
    password = str(getattr(credential, "password", "") or "")
    if not username or not password:
        for _suite_code, _case_code, _index, session in eligible:
            session["download_status"] = "not_configured"
            session["download_error"] = "未配置独立 BPR 凭据"
        return

    runtime = None
    try:
        bpr_env = replace(env, base_url=report_origin, username=username, password=password)
        login_session = CasAuthenticator(bpr_env).login(str(eligible[0][-1]["report_url"]))
        runtime = PlaywrightRuntime(bpr_env, login_session, headless=headless)
        runtime.start()
    except Exception as exc:
        error = _safe_error("BPR 登录", exc)
        for _suite_code, _case_code, _index, session in eligible:
            session["download_status"] = "failed"
            session["download_error"] = error
        if runtime is not None:
            try:
                runtime.stop()
            except Exception:
                pass
        return

    try:
        report_root = Path(report_dir).expanduser().resolve()
        artifact_root = (report_root / "artifacts").resolve()
        artifact_root.relative_to(report_root)
    except Exception as exc:
        error = _safe_error("BPR 下载", exc)
        for _suite_code, _case_code, _index, session in eligible:
            session["download_status"] = "failed"
            session["download_error"] = error
        try:
            runtime.stop()
        except Exception:
            pass
        return

    try:
        for suite_code, case_code, index, session in eligible:
            try:
                bpr_id = str(session.get("bpr_id") or "")
                target = (
                    artifact_root
                    / suite_code
                    / case_code
                    / "bpr"
                    / f"{index}-{_safe_path_part(bpr_id)}.html"
                ).resolve()
                target.relative_to(artifact_root)
                target.parent.mkdir(parents=True, exist_ok=True)
                downloaded = Path(
                    runtime.download_bpr_report(session["report_url"], bpr_id, target)
                ).expanduser().resolve()
                downloaded.relative_to(artifact_root)
                if downloaded != target:
                    raise ValueError("BPR 下载文件未保存到预期报告路径")
                report_file_href = downloaded.relative_to(report_root).as_posix()
            except Exception as exc:
                session["download_status"] = "failed"
                session["download_error"] = _safe_error("BPR 下载", exc)
                continue

            session["report_file"] = str(downloaded)
            session["report_file_href"] = report_file_href
            session["download_status"] = "downloaded"
            try:
                summary = extract_server_summary(downloaded)
            except Exception as exc:
                session["summary_status"] = "failed"
                session["summary_error"] = _safe_error("BPR 概要解析", exc)
                continue
            session["server_summary"] = {
                field: summary.get(field, "") for field, _label in SERVER_SUMMARY_FIELDS
            }
            session["summary_status"] = "parsed" if len(summary) == len(SERVER_SUMMARY_FIELDS) else "partial"
    finally:
        try:
            runtime.stop()
        except Exception:
            pass


def _safe_error(stage: str, exc: Exception) -> str:
    return f"{stage}: {exc.__class__.__name__}"


def _report_origin(report_url: str) -> str:
    if any(character.isspace() for character in report_url):
        return ""
    try:
        parsed = urlparse(report_url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return ""
    if parsed.scheme.lower() != "https" or not parsed.netloc or not hostname:
        return ""
    if parsed.username is not None or parsed.password is not None:
        return ""
    host = f"[{hostname.lower()}]" if ":" in hostname else hostname.lower()
    return f"https://{host}" + (f":{port}" if port and port != 443 else "")
