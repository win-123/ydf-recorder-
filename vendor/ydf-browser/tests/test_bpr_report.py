from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY

import pytest

import ydf_browser.bpr_report as bpr_report_module
from ydf_browser.bpr_report import SERVER_SUMMARY_FIELDS, extract_server_summary
from ydf_browser.config import EnvironmentConfig, UserCredential


FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_server_summary_reads_all_fixed_visible_values() -> None:
    summary = extract_server_summary(FIXTURES / "bpr_server_summary.html")

    assert summary["totalCostTime"] == "125"
    assert summary["totalSqlCostTime"] == "30 / 4"
    assert tuple(summary) == tuple(field for field, _label in SERVER_SUMMARY_FIELDS)
    assert SERVER_SUMMARY_FIELDS == (
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


def test_extract_server_summary_ignores_unknown_and_uses_only_first_row(tmp_path: Path) -> None:
    report = tmp_path / "partial.html"
    report.write_text(
        """<div id="summary-posi"><table>
        <tr><td data-field="totalCostTime"><span>12</span> / <em>3</em></td><td data-field="appCostTime"> </td><th data-field="unknown">ignore</th></tr>
        <tr><td data-field="appCostTime">must not read</td></tr>
        </table></div>""",
        encoding="utf-8",
    )

    assert extract_server_summary(report) == {"totalCostTime": "12 / 3"}


def test_extract_server_summary_rejects_missing_summary(tmp_path: Path) -> None:
    report = tmp_path / "missing.html"
    report.write_text("<table><tr><td data-field=\"totalCostTime\">125</td></tr></table>", encoding="utf-8")

    with pytest.raises(ValueError, match="BPR 文件中未找到服务端概要"):
        extract_server_summary(report)


def test_extract_server_summary_rejects_only_empty_fixed_cells(tmp_path: Path) -> None:
    report = tmp_path / "empty.html"
    report.write_text(
        '<div id="summary-posi"><table><tr><td data-field="totalCostTime"> <span> </span> </td></tr></table></div>',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="BPR 文件中未找到服务端概要"):
        extract_server_summary(report)


def test_extract_server_summary_skips_script_and_style_text(tmp_path: Path) -> None:
    report = tmp_path / "visible.html"
    report.write_text(
        '<div id="summary-posi"><table><tr><td data-field="totalCostTime">12<script>secret()</script><style>.x{display:none}</style><span> ms</span></td></tr></table></div>',
        encoding="utf-8",
    )

    assert extract_server_summary(report) == {"totalCostTime": "12 ms"}


def _result_with_sessions(*sessions: dict) -> dict:
    session_list = list(sessions)
    return {
        "success": True,
        "run": {"id": "run-1"},
        "suite_reports": [
            {
                "suite": {"code": "suite/A"},
                "case_reports": [
                    {
                        "case": {"code": "case A"},
                        "success": True,
                        "status": "passed",
                        "bpr_sessions": session_list,
                        "report": {"success": True, "bpr_sessions": session_list},
                    }
                ],
            }
        ],
    }


def _env(bpr: UserCredential | None = None) -> EnvironmentConfig:
    return EnvironmentConfig(
        env_name="ydf",
        base_url="https://example.yonyougov.top",
        sysid="yonbip",
        username="business-user",
        password="business-password",
        bpr=bpr,
    )


def test_enrich_bpr_reports_checks_report_url_before_missing_credentials(tmp_path: Path, monkeypatch) -> None:
    result = _result_with_sessions(
        {"index": 1, "bpr_id": "missing-url", "success": False},
        {
            "index": 2,
            "bpr_id": "has-url",
            "report_url": "https://example.yonyougov.top/bpr?pk=has-url",
            "success": True,
        },
    )
    monkeypatch.setattr(
        bpr_report_module,
        "CasAuthenticator",
        lambda *_args: pytest.fail("未配置凭据时不得登录"),
        raising=False,
    )

    bpr_report_module.enrich_bpr_reports(result, _env(), tmp_path, headless=True)

    missing_url, not_configured = result["suite_reports"][0]["case_reports"][0]["bpr_sessions"]
    assert missing_url["download_status"] == "failed"
    assert missing_url["summary_status"] == "not_attempted"
    assert "report_url" in missing_url["download_error"]
    assert not_configured["download_status"] == "not_configured"
    assert not_configured["summary_status"] == "not_attempted"
    for session in (missing_url, not_configured):
        assert session["report_file"] == ""
        assert session["report_file_href"] == ""
        assert session["summary_error"] == ""
        assert session["server_summary"] == {}


def test_enrich_bpr_reports_logs_in_once_downloads_sequentially_and_parses_statuses(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sessions = [
        {
            "index": 1,
            "bpr_id": "first/id",
            "report_url": "https://reports.example.test/bpr?pk=report-record-1",
            "success": True,
        },
        {
            "index": 2,
            "bpr_id": "second",
            "report_url": "https://reports.example.test/bpr?pk=report-record-2",
            "success": True,
        },
    ]
    result = _result_with_sessions(*sessions)
    calls: list[object] = []

    class _Authenticator:
        def __init__(self, env) -> None:
            calls.append(("auth", env.base_url, env.username, env.password))

        def login(self, entry_url=None):
            calls.append(("login", entry_url))
            return SimpleNamespace(cookies=[])

    class _Runtime:
        def __init__(self, env, session, *, headless) -> None:
            calls.append(("runtime", env.base_url, env.username, env.password, session, headless))

        def start(self) -> None:
            calls.append("start")

        def download_bpr_report(self, report_url, bpr_id, target):
            calls.append(("download", report_url, bpr_id, target))
            target.parent.mkdir(parents=True, exist_ok=True)
            if bpr_id == "first/id":
                target.write_bytes((FIXTURES / "bpr_server_summary.html").read_bytes())
            else:
                target.write_text(
                    '<div id="summary-posi"><table><tr><td data-field="totalCostTime">12</td></tr></table></div>',
                    encoding="utf-8",
                )
            target.chmod(0o600)
            return target

        def stop(self) -> None:
            calls.append("stop")

    monkeypatch.setattr(bpr_report_module, "CasAuthenticator", _Authenticator, raising=False)
    monkeypatch.setattr(bpr_report_module, "PlaywrightRuntime", _Runtime, raising=False)

    bpr_report_module.enrich_bpr_reports(
        result,
        _env(UserCredential("bpr-user", "bpr-password")),
        tmp_path,
        headless=False,
    )

    assert calls[:4] == [
        ("auth", "https://reports.example.test", "bpr-user", "bpr-password"),
        ("login", "https://reports.example.test/bpr?pk=report-record-1"),
        ("runtime", "https://reports.example.test", "bpr-user", "bpr-password", ANY, False),
        "start",
    ]
    assert [call[1] for call in calls if isinstance(call, tuple) and call[0] == "download"] == [
        "https://reports.example.test/bpr?pk=report-record-1",
        "https://reports.example.test/bpr?pk=report-record-2",
    ]
    assert [call[2] for call in calls if isinstance(call, tuple) and call[0] == "download"] == [
        "first/id",
        "second",
    ]
    assert calls[-1] == "stop"
    first, second = sessions
    assert first["download_status"] == second["download_status"] == "downloaded"
    assert first["summary_status"] == "parsed"
    assert second["summary_status"] == "partial"
    assert tuple(first["server_summary"]) == tuple(field for field, _label in SERVER_SUMMARY_FIELDS)
    assert second["server_summary"]["totalCostTime"] == "12"
    assert second["server_summary"]["appCostTime"] == ""
    for session in sessions:
        report_file = Path(session["report_file"])
        assert report_file.is_absolute()
        assert report_file.is_file()
        assert report_file.stat().st_mode & 0o777 == 0o600
        assert session["report_file_href"].startswith("artifacts/suite_A/case_A/bpr/")
        assert "diagnostic_files" not in session
    assert first["report_file_href"].endswith("1-first_id.html")
    assert result["success"] is True
    assert result["suite_reports"][0]["case_reports"][0]["success"] is True


@pytest.mark.parametrize(
    "report_url",
    [
        "http://reports.example.test/bpr?pk=record",
        "https://user:password@reports.example.test/bpr?pk=record",
        " https://reports.example.test/bpr?pk=record",
        "/bpr?pk=record",
        "//reports.example.test/bpr?pk=record",
    ],
)
def test_enrich_bpr_reports_rejects_unsafe_report_url_before_login(
    report_url: str,
    tmp_path: Path,
    monkeypatch,
) -> None:
    session = {"index": 1, "bpr_id": "bpr-1", "report_url": report_url, "success": True}
    result = _result_with_sessions(session)
    monkeypatch.setattr(
        bpr_report_module,
        "CasAuthenticator",
        lambda *_args: pytest.fail("不安全 report_url 不得接触 BPR 凭据"),
    )

    bpr_report_module.enrich_bpr_reports(
        result,
        _env(UserCredential("private-user", "private-password")),
        tmp_path,
        headless=True,
    )

    assert session["download_status"] == "failed"
    assert session["summary_status"] == "not_attempted"
    assert session["report_file"] == ""
    assert report_url not in session["download_error"]
    assert "private-user" not in str(session)
    assert "private-password" not in str(session)


def test_enrich_bpr_reports_rejects_other_origin_without_second_login_or_download(
    tmp_path: Path,
    monkeypatch,
) -> None:
    first_url = "https://reports.example.test/bpr?pk=report-record-1"
    other_url = "https://other.example.test/bpr?pk=report-record-2"
    first = {"index": 1, "bpr_id": "first", "report_url": first_url, "success": True}
    other = {"index": 2, "bpr_id": "other", "report_url": other_url, "success": True}
    result = _result_with_sessions(first, other)
    calls: list[object] = []

    class _Authenticator:
        def __init__(self, env) -> None:
            calls.append(("auth", env.base_url))

        def login(self, entry_url=None):
            calls.append(("login", entry_url))
            return SimpleNamespace(cookies=[])

    def _download(report_url, _bpr_id, target):
        calls.append(("download", report_url))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((FIXTURES / "bpr_server_summary.html").read_bytes())
        target.chmod(0o600)
        return target

    monkeypatch.setattr(bpr_report_module, "CasAuthenticator", _Authenticator)
    monkeypatch.setattr(
        bpr_report_module,
        "PlaywrightRuntime",
        lambda *_args, **_kwargs: SimpleNamespace(
            start=lambda: calls.append("start"),
            stop=lambda: calls.append("stop"),
            download_bpr_report=_download,
        ),
    )

    bpr_report_module.enrich_bpr_reports(
        result,
        _env(UserCredential("private-user", "private-password")),
        tmp_path,
        headless=True,
    )

    assert calls == [
        ("auth", "https://reports.example.test"),
        ("login", first_url),
        "start",
        ("download", first_url),
        "stop",
    ]
    assert first["download_status"] == "downloaded"
    assert other["download_status"] == "failed"
    assert other["summary_status"] == "not_attempted"
    assert other_url not in other["download_error"]
    assert "private-user" not in str(other)
    assert "private-password" not in str(other)


def test_enrich_bpr_reports_redacts_login_failure_without_changing_business_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session = {
        "index": 1,
        "bpr_id": "bpr-1",
        "report_url": "https://example.yonyougov.top/bpr?pk=bpr-1",
        "success": True,
    }
    result = _result_with_sessions(session)

    class _Authenticator:
        def __init__(self, _env) -> None:
            pass

        def login(self, _entry_url=None):
            raise RuntimeError('{"response":"username=foo password=foobar private login body"}')

    monkeypatch.setattr(bpr_report_module, "CasAuthenticator", _Authenticator, raising=False)

    bpr_report_module.enrich_bpr_reports(
        result,
        _env(UserCredential("foo", "foobar")),
        tmp_path,
        headless=True,
    )

    assert session["download_status"] == "failed"
    assert session["summary_status"] == "not_attempted"
    assert session["download_error"] == "BPR 登录: RuntimeError"
    serialized = str(session)
    assert "private login body" not in serialized
    assert "foo" not in serialized
    assert "foobar" not in serialized
    assert result["success"] is True
    assert result["suite_reports"][0]["case_reports"][0]["status"] == "passed"


def test_enrich_bpr_reports_records_download_failures_and_stops_runtime(tmp_path: Path, monkeypatch) -> None:
    sessions = [
        {
            "index": index,
            "bpr_id": f"bpr-{index}",
            "report_url": f"https://example.yonyougov.top/bpr?pk=bpr-{index}",
            "success": True,
        }
        for index in (1, 2)
    ]
    result = _result_with_sessions(*sessions)
    calls: list[str] = []
    monkeypatch.setattr(
        bpr_report_module,
        "CasAuthenticator",
        lambda _env: SimpleNamespace(login=lambda _entry_url=None: SimpleNamespace(cookies=[])),
    )

    class _Runtime:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def start(self) -> None:
            calls.append("start")

        def download_bpr_report(self, _url, bpr_id, _target):
            calls.append(bpr_id)
            raise RuntimeError('{"response":"username=foo password=foobar private download body"}')

        def stop(self) -> None:
            calls.append("stop")

    monkeypatch.setattr(bpr_report_module, "PlaywrightRuntime", _Runtime)

    bpr_report_module.enrich_bpr_reports(
        result,
        _env(UserCredential("foo", "foobar")),
        tmp_path,
        headless=True,
    )

    assert calls == ["start", "bpr-1", "bpr-2", "stop"]
    for session in sessions:
        assert session["download_status"] == "failed"
        assert session["summary_status"] == "not_attempted"
        assert session["download_error"] == "BPR 下载: RuntimeError"
        assert "private download body" not in str(session)
        assert "foo" not in str(session)
        assert "foobar" not in str(session)
    assert result["success"] is True
    assert result["suite_reports"][0]["case_reports"][0]["status"] == "passed"


def test_enrich_bpr_reports_keeps_download_when_summary_parse_fails(tmp_path: Path, monkeypatch) -> None:
    session = {
        "index": 1,
        "bpr_id": "bpr-1",
        "report_url": "https://example.yonyougov.top/bpr?pk=bpr-1",
        "success": True,
    }
    result = _result_with_sessions(session)

    monkeypatch.setattr(
        bpr_report_module,
        "CasAuthenticator",
        lambda _env: SimpleNamespace(login=lambda _entry_url=None: SimpleNamespace(cookies=[])),
        raising=False,
    )

    class _Runtime:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def start(self) -> None:
            pass

        def download_bpr_report(self, _url, _bpr_id, target):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("<html>raw private body</html>", encoding="utf-8")
            target.chmod(0o600)
            return target

        def stop(self) -> None:
            pass

    monkeypatch.setattr(bpr_report_module, "PlaywrightRuntime", _Runtime, raising=False)
    monkeypatch.setattr(
        bpr_report_module,
        "extract_server_summary",
        lambda _path: (_ for _ in ()).throw(
            ValueError('{"response":"username=foo password=foobar private parser body"}')
        ),
    )

    bpr_report_module.enrich_bpr_reports(
        result,
        _env(UserCredential("foo", "foobar")),
        tmp_path,
        headless=True,
    )

    assert session["download_status"] == "downloaded"
    assert session["summary_status"] == "failed"
    assert session["server_summary"] == {}
    assert session["summary_error"] == "BPR 概要解析: ValueError"
    assert "raw private body" not in session["summary_error"]
    assert "private parser body" not in str(session)
    assert "foo" not in str(session)
    assert "foobar" not in str(session)
    assert Path(session["report_file"]).read_text(encoding="utf-8") == "<html>raw private body</html>"


def test_enrich_bpr_reports_keeps_dot_segments_inside_artifact_root(tmp_path: Path, monkeypatch) -> None:
    session = {
        "index": 1,
        "bpr_id": "..",
        "report_url": "https://example.yonyougov.top/bpr?pk=..",
        "success": True,
    }
    result = _result_with_sessions(session)
    result["suite_reports"][0]["suite"]["code"] = "."
    result["suite_reports"][0]["case_reports"][0]["case"]["code"] = ".."
    monkeypatch.setattr(
        bpr_report_module,
        "CasAuthenticator",
        lambda _env: SimpleNamespace(login=lambda _entry_url=None: SimpleNamespace(cookies=[])),
    )

    def _download(_url, _bpr_id, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((FIXTURES / "bpr_server_summary.html").read_bytes())
        target.chmod(0o600)
        return target

    monkeypatch.setattr(
        bpr_report_module,
        "PlaywrightRuntime",
        lambda *_args, **_kwargs: SimpleNamespace(start=lambda: None, stop=lambda: None, download_bpr_report=_download),
    )

    bpr_report_module.enrich_bpr_reports(
        result,
        _env(UserCredential("foo", "foobar")),
        tmp_path,
        headless=True,
    )

    expected = (tmp_path / "artifacts" / "unknown" / "unknown" / "bpr" / "1-unknown.html").resolve()
    assert Path(session["report_file"]) == expected
    assert session["report_file_href"] == "artifacts/unknown/unknown/bpr/1-unknown.html"
    assert expected.is_file()


def test_enrich_bpr_reports_isolates_relative_path_failure_per_session(tmp_path: Path, monkeypatch) -> None:
    session = {
        "index": 1,
        "bpr_id": "bpr-1",
        "report_url": "https://example.yonyougov.top/bpr?pk=bpr-1",
        "success": True,
    }
    result = _result_with_sessions(session)
    monkeypatch.setattr(
        bpr_report_module,
        "CasAuthenticator",
        lambda _env: SimpleNamespace(login=lambda _entry_url=None: SimpleNamespace(cookies=[])),
    )

    def _download(_url, _bpr_id, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((FIXTURES / "bpr_server_summary.html").read_bytes())
        return target

    monkeypatch.setattr(
        bpr_report_module,
        "PlaywrightRuntime",
        lambda *_args, **_kwargs: SimpleNamespace(start=lambda: None, stop=lambda: None, download_bpr_report=_download),
    )
    original_relative_to = Path.relative_to

    def _relative_to(self, *other, **kwargs):
        if self.suffix == ".html":
            raise ValueError('{"response":"private relative path body"}')
        return original_relative_to(self, *other, **kwargs)

    monkeypatch.setattr(Path, "relative_to", _relative_to)

    bpr_report_module.enrich_bpr_reports(
        result,
        _env(UserCredential("foo", "foobar")),
        tmp_path,
        headless=True,
    )

    assert session["download_status"] == "failed"
    assert session["summary_status"] == "not_attempted"
    assert session["download_error"] == "BPR 下载: ValueError"
    assert "private relative path body" not in str(session)
    assert result["success"] is True
    assert result["suite_reports"][0]["case_reports"][0]["status"] == "passed"
