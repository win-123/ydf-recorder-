from __future__ import annotations

import os
from contextlib import contextmanager

import pytest

from ydf_browser.auth import AuthenticationError, CasAuthenticator
from ydf_browser.config import EnvironmentConfig


class _FakeCookies:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def clear(self) -> None:
        self.events.append("clear")

    def update(self, other) -> None:
        self.events.append("update")

    def __iter__(self):
        return iter([])


class _FakeResponse:
    def __init__(
        self,
        *,
        text: str = "",
        status_code: int = 200,
        headers: dict | None = None,
        url: str = "",
        content: bytes = b"",
        json_payload: dict | None = None,
    ) -> None:
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}
        self.url = url
        self.content = content
        self._json_payload = json_payload

    def raise_for_status(self) -> None:
        return

    def json(self) -> dict:
        if self._json_payload is None:
            raise ValueError("no json payload")
        return self._json_payload


class _FakeSession:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.trust_env = True
        self.headers = {}
        self.cookies = _FakeCookies(events)

    def get(self, url: str, **kwargs):
        self.events.append(f"get:{url}")
        if "cas/login" in url:
            return _FakeResponse(
                text=(
                    "var randomvalue = 'r';"
                    "var modulus = 'ab';"
                    "var exponent = '10001';"
                )
            )
        return _FakeResponse()

    def post(self, url: str, **kwargs):
        self.events.append(f"post:{url}")
        return _FakeResponse(status_code=302, headers={"Location": "/login-success"})


class _RequestBackedFakeSession(_FakeSession):
    def __init__(self, events: list[str]) -> None:
        super().__init__(events)
        self.sslkeylogfile_values: list[str | None] = []

    def request(self, method: str, url: str, **kwargs):
        self.sslkeylogfile_values.append(os.environ.get("SSLKEYLOGFILE"))
        self.events.append(f"request:{method}:{url}")
        if method == "GET" and "cas/login" in url:
            return _FakeResponse(
                text=(
                    "var randomvalue = 'r';"
                    "var modulus = 'ab';"
                    "var exponent = '10001';"
                )
            )
        if method == "POST":
            return _FakeResponse(status_code=302, headers={"Location": "/login-success"})
        return _FakeResponse()

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)


@contextmanager
def _noop_contextmanager():
    yield


def test_cas_authenticator_login_clears_session_cookies_before_requests(monkeypatch) -> None:
    events: list[str] = []
    fake_session = _FakeSession(events)
    monkeypatch.setattr("ydf_browser.auth.requests.Session", lambda: fake_session)
    monkeypatch.setattr("ydf_browser.auth.temporarily_disable_sslkeylogfile", _noop_contextmanager)

    authenticator = CasAuthenticator(
        EnvironmentConfig(
            env_name="ydf",
            base_url="https://example.yonyougov.top",
            sysid="yonbip",
            username="demo",
            password="demo",
        )
    )

    session = authenticator.login()

    assert session is fake_session
    assert events[0] == "clear"
    assert events[1].startswith("get:https://example.yonyougov.top/cas/login")


def test_cas_authenticator_login_disables_requests_environment_proxy_inheritance(monkeypatch) -> None:
    events: list[str] = []
    fake_session = _FakeSession(events)
    monkeypatch.setattr("ydf_browser.auth.requests.Session", lambda: fake_session)
    monkeypatch.setattr("ydf_browser.auth.temporarily_disable_sslkeylogfile", _noop_contextmanager)

    authenticator = CasAuthenticator(
        EnvironmentConfig(
            env_name="ydf",
            base_url="https://example.yonyougov.top",
            sysid="yonbip",
            username="demo",
            password="demo",
        )
    )

    session = authenticator.login()

    assert session.trust_env is False


def test_cas_authenticator_regular_login_never_posts_to_redirected_cross_origin_url(monkeypatch) -> None:
    events: list[str] = []
    cross_origin_login_url = "https://accounts.example.test/cas/login"

    class _RedirectedSession(_FakeSession):
        def get(self, url: str, **kwargs):
            self.events.append(f"get:{url}")
            if "cas/login" in url:
                return _FakeResponse(
                    url=cross_origin_login_url,
                    text="var randomvalue = 'r';var modulus = 'ab';var exponent = '10001';",
                )
            return _FakeResponse(url=url)

    fake_session = _RedirectedSession(events)
    monkeypatch.setattr("ydf_browser.auth.requests.Session", lambda: fake_session)
    monkeypatch.setattr("ydf_browser.auth.temporarily_disable_sslkeylogfile", _noop_contextmanager)
    authenticator = CasAuthenticator(
        EnvironmentConfig(
            env_name="ydf",
            base_url="https://example.yonyougov.top",
            sysid="yonbip",
            username="demo",
            password="demo",
        )
    )
    requested_url = authenticator.build_login_url()

    authenticator.login()

    assert f"post:{requested_url}" in events
    assert f"post:{cross_origin_login_url}" not in events


def test_cas_authenticator_uses_same_origin_login_reached_from_entry_url(monkeypatch) -> None:
    events: list[str] = []
    entry_url = "https://reports.example.test/iuap-ymc-server/proxy/server/bpr/open?pk=record"
    login_url = (
        "https://reports.example.test/cas/login?service="
        "https%3A%2F%2Freports.example.test%2Fiuap-ymc-server%2Fsecurity%2Fauthorize"
    )

    class _EntrySession(_FakeSession):
        def get(self, url: str, **kwargs):
            self.events.append(f"get:{url}")
            if url == entry_url:
                return _FakeResponse(
                    url=login_url,
                    text="var randomvalue = 'r';var modulus = 'ab';var exponent = '10001';",
                )
            return _FakeResponse(url=url)

    fake_session = _EntrySession(events)
    monkeypatch.setattr("ydf_browser.auth.requests.Session", lambda: fake_session)
    monkeypatch.setattr("ydf_browser.auth.temporarily_disable_sslkeylogfile", _noop_contextmanager)
    authenticator = CasAuthenticator(
        EnvironmentConfig(
            env_name="bpr",
            base_url="https://reports.example.test",
            sysid="yonbip",
            username="bpr-user",
            password="bpr-password",
        )
    )

    authenticator.login(entry_url)

    assert events[1] == f"get:{entry_url}"
    assert events[2] == f"post:{login_url}"


def test_cas_authenticator_rejects_cross_origin_entry_redirect_before_post(monkeypatch) -> None:
    events: list[str] = []
    entry_url = "https://reports.example.test/iuap-ymc-server/proxy/server/bpr/open?pk=record"

    class _CrossOriginSession(_FakeSession):
        def get(self, url: str, **kwargs):
            self.events.append(f"get:{url}")
            return _FakeResponse(
                url="https://other.example.test/cas/login",
                text="var randomvalue = 'r';var modulus = 'ab';var exponent = '10001';",
            )

    fake_session = _CrossOriginSession(events)
    monkeypatch.setattr("ydf_browser.auth.requests.Session", lambda: fake_session)
    monkeypatch.setattr("ydf_browser.auth.temporarily_disable_sslkeylogfile", _noop_contextmanager)
    authenticator = CasAuthenticator(
        EnvironmentConfig(
            env_name="bpr",
            base_url="https://reports.example.test",
            sysid="yonbip",
            username="bpr-user",
            password="bpr-password",
        )
    )

    with pytest.raises(AuthenticationError, match="同源"):
        authenticator.login(entry_url)

    assert not any(event.startswith("post:") for event in events)


def test_cas_authenticator_session_requests_temporarily_disable_sslkeylogfile(monkeypatch) -> None:
    events: list[str] = []
    fake_session = _RequestBackedFakeSession(events)
    monkeypatch.setattr("ydf_browser.auth.requests.Session", lambda: fake_session)
    monkeypatch.setenv("SSLKEYLOGFILE", "/forbidden/sslkeylogfile.txt")

    authenticator = CasAuthenticator(
        EnvironmentConfig(
            env_name="ydf",
            base_url="https://example.yonyougov.top",
            sysid="yonbip",
            username="demo",
            password="demo",
        )
    )

    session = authenticator.login()
    session.get("https://example.yonyougov.top/after-login")

    assert fake_session.sslkeylogfile_values == [None, None, None, None]
    assert os.environ["SSLKEYLOGFILE"] == "/forbidden/sslkeylogfile.txt"


_LOGIN_PARAMS_HTML = "var randomvalue='r';var modulus='ab';var exponent='10001';"
_TFA_HTML = (
    "var tfaMobile = '+86 139****2316';"
    "var tfaEmail = 'zw_yhtmanag*****@yonyou.com';"
    "var tfaId = 'tfa0065c-d6ca-4dc3-aa61-ff20f4a4daf0';"
    '<input id="validateImageInput">'
    '<img src="/cas/images/getValiImage111111111111">'
    '<span onclick="sendTfaCode()">获取验证码</span>'
)


class _TfaSession(_FakeSession):
    def __init__(
        self,
        events: list[str],
        send_sequence: list[dict] | None = None,
        tfa_html: str = _TFA_HTML,
    ) -> None:
        super().__init__(events)
        self.send_sequence = list(send_sequence or [{"status": 1, "msg": "success"}])
        self.tfa_html = tfa_html
        self.posted_bodies: list[dict | None] = []

    def get(self, url: str, **kwargs):
        self.events.append(f"get:{url}")
        if "cas/login" in url:
            return _FakeResponse(text=_LOGIN_PARAMS_HTML)
        if "getValiImage" in url:
            return _FakeResponse(content=b"\x89PNG\r\n\x1a\nfake-captcha")
        return _FakeResponse()

    def post(self, url: str, **kwargs):
        self.events.append(f"post:{url}")
        self.posted_bodies.append(kwargs.get("data"))
        if "sendTfaCode" in url:
            return _FakeResponse(json_payload=self.send_sequence.pop(0))
        if "tfaLogin" in url:
            return _FakeResponse(status_code=302, headers={"Location": "/login-success"})
        if "cas/login" in url:
            return _FakeResponse(text=self.tfa_html)
        return _FakeResponse(status_code=302, headers={"Location": "/login-success"})


def _make_tfa_authenticator(sms_verify_code: str = "666666") -> CasAuthenticator:
    return CasAuthenticator(
        EnvironmentConfig(
            env_name="ydf",
            base_url="https://example.yonyougov.top",
            sysid="yonbip",
            username="demo",
            password="demo",
            sms_verify_code=sms_verify_code,
        )
    )


def test_cas_authenticator_completes_sms_tfa_login(monkeypatch) -> None:
    events: list[str] = []
    fake_session = _TfaSession(events)
    monkeypatch.setattr("ydf_browser.auth.requests.Session", lambda: fake_session)
    monkeypatch.setattr("ydf_browser.auth.temporarily_disable_sslkeylogfile", _noop_contextmanager)
    monkeypatch.setattr("ydf_browser.auth.captcha_classifier", lambda: (lambda image: "abcd"))

    session = _make_tfa_authenticator().login()

    assert session is fake_session
    assert any("getValiImage" in event for event in events)
    sent = fake_session.posted_bodies[1]
    assert sent["code"] == "abcd"
    assert sent["tfaType"] == "mobile"
    assert sent["tfaId"] == "tfa0065c-d6ca-4dc3-aa61-ff20f4a4daf0"
    assert any("tfaLogin" in event for event in events)
    final = fake_session.posted_bodies[2]
    assert final["tfaValidateCode"] == "666666"
    assert any(event.startswith("get:") and "login-success" in event for event in events)


def test_cas_authenticator_retries_captcha_recognition(monkeypatch) -> None:
    events: list[str] = []
    fake_session = _TfaSession(events, send_sequence=[{"status": 0, "codemsg": "codeError"}, {"status": 1}])
    monkeypatch.setattr("ydf_browser.auth.requests.Session", lambda: fake_session)
    monkeypatch.setattr("ydf_browser.auth.temporarily_disable_sslkeylogfile", _noop_contextmanager)
    calls: list[str] = []

    def fake_ocr(image: bytes) -> str:
        calls.append("ocr")
        return "wxyz"

    monkeypatch.setattr("ydf_browser.auth.captcha_classifier", lambda: fake_ocr)

    _make_tfa_authenticator().login()

    assert calls == ["ocr", "ocr"]
    assert sum("getValiImage" in event for event in events) == 2
    assert sum("sendTfaCode" in event for event in events) == 2


def test_cas_authenticator_waits_once_then_retries_rate_limited_sms(monkeypatch) -> None:
    events: list[str] = []
    fake_session = _TfaSession(
        events,
        send_sequence=[{"status": 0, "codemsg": "1分钟内不能重复发送"}, {"status": 1}],
    )
    monkeypatch.setattr("ydf_browser.auth.requests.Session", lambda: fake_session)
    monkeypatch.setattr("ydf_browser.auth.temporarily_disable_sslkeylogfile", _noop_contextmanager)
    monkeypatch.setattr("ydf_browser.auth.captcha_classifier", lambda: (lambda image: "abcd"))
    waits: list[int] = []
    monkeypatch.setattr("ydf_browser.auth._sms_retry_wait", lambda seconds: waits.append(seconds))

    _make_tfa_authenticator().login()

    assert waits == [70]
    assert sum("sendTfaCode" in event for event in events) == 2


def test_cas_authenticator_reports_persistent_sms_rate_limit(monkeypatch) -> None:
    events: list[str] = []
    fake_session = _TfaSession(
        events,
        send_sequence=[{"status": 0, "codemsg": "sendmore2"}, {"status": 0, "codemsg": "sendmore2"}],
    )
    monkeypatch.setattr("ydf_browser.auth.requests.Session", lambda: fake_session)
    monkeypatch.setattr("ydf_browser.auth.temporarily_disable_sslkeylogfile", _noop_contextmanager)
    monkeypatch.setattr("ydf_browser.auth.captcha_classifier", lambda: (lambda image: "abcd"))
    monkeypatch.setattr("ydf_browser.auth._sms_retry_wait", lambda seconds: None)

    with pytest.raises(AuthenticationError, match="限流"):
        _make_tfa_authenticator().login()


def test_cas_authenticator_disabled_sms_flow_never_sends_code(monkeypatch) -> None:
    events: list[str] = []
    fake_session = _TfaSession(events)
    monkeypatch.setattr("ydf_browser.auth.requests.Session", lambda: fake_session)
    monkeypatch.setattr("ydf_browser.auth.temporarily_disable_sslkeylogfile", _noop_contextmanager)

    with pytest.raises(AuthenticationError, match="未启用自动短信流程"):
        _make_tfa_authenticator(sms_verify_code="").login()

    assert not any("getValiImage" in event for event in events)
    assert not any("sendTfaCode" in event for event in events)


def test_cas_authenticator_rejects_non_mobile_tfa_page(monkeypatch) -> None:
    events: list[str] = []
    email_only_html = _TFA_HTML.replace("var tfaMobile = '+86 139****2316';", "")
    fake_session = _TfaSession(events, tfa_html=email_only_html)
    monkeypatch.setattr("ydf_browser.auth.requests.Session", lambda: fake_session)
    monkeypatch.setattr("ydf_browser.auth.temporarily_disable_sslkeylogfile", _noop_contextmanager)
    monkeypatch.setattr("ydf_browser.auth.captcha_classifier", lambda: (lambda image: "abcd"))

    with pytest.raises(AuthenticationError, match="仅支持手机短信多因子验证"):
        _make_tfa_authenticator().login()


def test_cas_authenticator_missing_ocr_dependency_gives_install_hint(monkeypatch) -> None:
    import sys

    events: list[str] = []
    fake_session = _TfaSession(events)
    monkeypatch.setattr("ydf_browser.auth.requests.Session", lambda: fake_session)
    monkeypatch.setattr("ydf_browser.auth.temporarily_disable_sslkeylogfile", _noop_contextmanager)
    monkeypatch.setitem(sys.modules, "ddddocr", None)
    monkeypatch.setattr("ydf_browser.captcha._ocr", None)
    monkeypatch.delenv("YDF_BROWSER_INSTALL_OCR", raising=False)

    with pytest.raises(AuthenticationError, match="--install-ocr"):
        _make_tfa_authenticator().login()


def test_cas_authenticator_reuses_existing_session_cookies(monkeypatch) -> None:
    events: list[str] = []
    fake_session = _TfaSession(events)
    monkeypatch.setattr("ydf_browser.auth.requests.Session", lambda: fake_session)
    monkeypatch.setattr("ydf_browser.auth.temporarily_disable_sslkeylogfile", _noop_contextmanager)
    monkeypatch.setattr("ydf_browser.auth.captcha_classifier", lambda: (lambda image: "abcd"))

    previous = _TfaSession(["previous-events"])
    _make_tfa_authenticator().login(existing_session=previous)

    assert "clear" not in events
    assert "update" in events
    assert events[0] == "update"


def test_cas_authenticator_follows_ticket_directly_when_session_reused(monkeypatch) -> None:
    events: list[str] = []

    class _TicketSession(_FakeSession):
        def get(self, url: str, **kwargs):
            self.events.append(f"get:{url}")
            if "login-success" in url:
                return _FakeResponse()
            return _FakeResponse(text='<script>window.location = "/cas-after?ticket=ST-123"</script>')

    fake_session = _TicketSession(events)
    monkeypatch.setattr("ydf_browser.auth.requests.Session", lambda: fake_session)
    monkeypatch.setattr("ydf_browser.auth.temporarily_disable_sslkeylogfile", _noop_contextmanager)

    previous = _FakeSession([])
    _make_tfa_authenticator().login(existing_session=previous)

    assert not any(event.startswith("post:") for event in events)
    assert any("ticket=ST-123" in event for event in events)


@pytest.mark.parametrize('failure', [
    {'status': 0, 'codemsg': 'sendmore2'},
    {'status': 0, 'codemsg': 'sendmore5min'},
    {'status': 0, 'msg': '手机号在24小时内仅支持20次获取验证码'},
    {'status': 0, 'msg': '手机号在5分钟内仅支持2次获取验证码'},
    {'status': 0, 'msg': 'unknown secret-value'},
])
def test_sms_long_limits_and_unknown_failures_never_retry(monkeypatch, failure):
    events = []
    session = _TfaSession(events, send_sequence=[failure] * 4)
    monkeypatch.setattr('ydf_browser.auth.requests.Session', lambda: session)
    monkeypatch.setattr('ydf_browser.auth.captcha_classifier', lambda: (lambda image: 'abcd'))
    waits = []
    monkeypatch.setattr('ydf_browser.auth._sms_retry_wait', waits.append)
    with pytest.raises(AuthenticationError) as error:
        _make_tfa_authenticator().login()
    assert 'secret-value' not in str(error.value)
    assert sum('sendTfaCode' in event for event in events) == 1
    assert waits == []


def test_wrong_sms_code_does_not_reenter_send_flow(monkeypatch):
    events = []
    class WrongCodeSession(_TfaSession):
        def post(self, url, **kwargs):
            if 'tfaLogin' in url:
                self.events.append(f'post:{url}')
                return _FakeResponse(text=_TFA_HTML)
            return super().post(url, **kwargs)
    session = WrongCodeSession(events, send_sequence=[{'status': 1}] * 4)
    monkeypatch.setattr('ydf_browser.auth.requests.Session', lambda: session)
    monkeypatch.setattr('ydf_browser.auth.captcha_classifier', lambda: (lambda image: 'abcd'))
    with pytest.raises(AuthenticationError, match='短信验证'):
        _make_tfa_authenticator().login()
    assert sum('sendTfaCode' in event for event in events) == 1
    assert sum('tfaLogin' in event for event in events) == 1


@pytest.mark.parametrize('sequence,expected_sends,expected_waits', [
    ([{'status': 0, 'codemsg': 'codeError'}] * 3, 3, []),
    ([{'status': 0, 'codemsg': 'sendmore1'}] * 2, 2, [70]),
    ([{'status': 0, 'codemsg': 'codeError'}] * 2 + [{'status': 0, 'codemsg': 'sendmore1'}, {'status': 0, 'codemsg': 'codeError'}], 4, [70]),
])
def test_sms_attempts_have_a_global_bound(monkeypatch, sequence, expected_sends, expected_waits):
    events, waits = [], []
    session = _TfaSession(events, send_sequence=sequence)
    monkeypatch.setattr('ydf_browser.auth.requests.Session', lambda: session)
    monkeypatch.setattr('ydf_browser.auth.captcha_classifier', lambda: (lambda image: 'abcd'))
    monkeypatch.setattr('ydf_browser.auth._sms_retry_wait', waits.append)
    with pytest.raises(AuthenticationError):
        _make_tfa_authenticator().login()
    assert sum('sendTfaCode' in event for event in events) == expected_sends
    assert waits == expected_waits


@pytest.mark.parametrize('invalid', [[], None, {'status': False, 'msg': 'secret-value'}])
def test_sms_invalid_json_payload_fails_without_retry(monkeypatch, invalid):
    events = []
    session = _TfaSession(events, send_sequence=[invalid])
    monkeypatch.setattr('ydf_browser.auth.requests.Session', lambda: session)
    monkeypatch.setattr('ydf_browser.auth.captcha_classifier', lambda: (lambda image: 'abcd'))
    with pytest.raises(AuthenticationError) as exc:
        _make_tfa_authenticator().login()
    assert 'secret-value' not in str(exc.value)
    assert sum('sendTfaCode' in event for event in events) == 1


@pytest.mark.parametrize('image_status,image_type', [(500, 'image/png'), (302, 'text/html'), (200, 'text/html')])
def test_invalid_captcha_image_never_sends_sms(monkeypatch, image_status, image_type):
    events = []
    class BadImageSession(_TfaSession):
        def get(self, url, **kwargs):
            if 'getValiImage' in url:
                return _FakeResponse(status_code=image_status, content=b'secret-value', headers={'Content-Type': image_type})
            return super().get(url, **kwargs)
    monkeypatch.setattr('ydf_browser.auth.requests.Session', lambda: BadImageSession(events))
    monkeypatch.setattr('ydf_browser.auth.captcha_classifier', lambda: (lambda image: pytest.fail('must not OCR invalid response')))
    with pytest.raises(AuthenticationError) as exc:
        _make_tfa_authenticator().login()
    assert 'secret-value' not in str(exc.value)
    assert not any('sendTfaCode' in event for event in events)


def test_sms_ticket_redirect_is_same_origin_and_preserves_login_query(monkeypatch):
    from urllib.parse import urlsplit
    events = []
    class TicketSession(_TfaSession):
        def post(self, url, **kwargs):
            if 'tfaLogin' in url:
                assert urlsplit(url).query == urlsplit(_make_tfa_authenticator().build_login_url()).query
                return _FakeResponse(text='<script>window.location="https://other.test/?ticket=secret-value"</script>')
            return super().post(url, **kwargs)
    monkeypatch.setattr('ydf_browser.auth.requests.Session', lambda: TicketSession(events))
    monkeypatch.setattr('ydf_browser.auth.captcha_classifier', lambda: (lambda image: 'abcd'))
    with pytest.raises(AuthenticationError, match='同源') as exc:
        _make_tfa_authenticator().login()
    assert 'secret-value' not in str(exc.value)
    assert not any('other.test' in event for event in events)


def test_empty_mobile_does_not_send_sms(monkeypatch):
    events = []
    session = _TfaSession(events, tfa_html=_TFA_HTML.replace("var tfaMobile = '+86 139****2316';", "var tfaMobile = '';"))
    monkeypatch.setattr('ydf_browser.auth.requests.Session', lambda: session)
    with pytest.raises(AuthenticationError, match='仅支持手机'):
        _make_tfa_authenticator().login()
    assert not any('sendTfaCode' in event for event in events)
