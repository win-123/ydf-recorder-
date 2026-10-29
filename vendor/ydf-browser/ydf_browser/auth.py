from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlsplit, urlparse

import requests

from .config import EnvironmentConfig
from .captcha import CaptchaError, captcha_classifier


class AuthenticationError(RuntimeError):
    pass


class SessionExpired(AuthenticationError):
    """An authenticated request explicitly requires a new login."""


class PasswordExpiredError(AuthenticationError):
    pass


class SmsVerificationError(AuthenticationError):
    pass


@dataclass(slots=True)
class SessionState:
    base_url: str
    cookies: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"base_url": self.base_url, "cookies": self.cookies}


class CasAuthenticator:
    def __init__(self, config: EnvironmentConfig) -> None:
        self.config = config

    def build_login_url(self) -> str:
        service_url = (
            f"{self.config.base_url}/login_light"
            f"?yhtdesturl=/yhtssoislogin"
            f"&finger={self.config.finger}"
            f"&yhtrealservice={self.config.base_url}"
        )
        return (
            f"{self.config.base_url}/cas/login"
            f"?sysid={self.config.sysid}"
            f"&mode=light"
            f"&casLoginType=normal"
            f"&themeColor="
            f"&service={quote(service_url, safe='')}"
            f"&locale=zh_CN"
        )

    def login(
        self,
        entry_url: str | None = None,
        existing_session: requests.Session | None = None,
    ) -> requests.Session:
        session = _prepare_session(requests.Session())
        if existing_session is not None:
            session.cookies.update(existing_session.cookies)
        else:
            session.cookies.clear()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                )
            }
        )
        requested_url = entry_url or self.build_login_url()
        with temporarily_disable_sslkeylogfile():
            page = session.get(requested_url, timeout=20)
            page.raise_for_status()
            login_url = str(getattr(page, "url", "") or requested_url) if entry_url else requested_url
            if entry_url and not _same_https_origin(login_url, self.config.base_url):
                raise AuthenticationError("BPR 登录入口重定向到非同源地址")
            ticket_url = _extract_ticket_redirect(page.text)
            if ticket_url:
                if ticket_url.startswith("/"):
                    ticket_url = self._cas_url(login_url, ticket_url)
                session.get(ticket_url, allow_redirects=True, timeout=20)
                return session
            params = self.parse_login_page(page.text)
            form_data = self.build_form_data(params)
            response = session.post(login_url, data=form_data, allow_redirects=False, timeout=20)

            if response.status_code in (301, 302, 303, 307):
                location = response.headers.get("Location", "")
                if location.startswith("/"):
                    location = f"{self.config.base_url}{location}"
                if location:
                    session.get(location, allow_redirects=True, timeout=20)
                    return session

            if response.status_code == 200:
                self._handle_login_html(session, response.text, login_url)
                return session

        raise AuthenticationError(f"登录失败，状态码: {response.status_code}")

    def save_session(self, session: requests.Session, target: str | Path) -> Path:
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = SessionState(
            base_url=self.config.base_url,
            cookies=[
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                    "secure": bool(cookie.secure),
                    "expires": cookie.expires,
                }
                for cookie in session.cookies
            ],
        )
        path.write_text(json.dumps(data.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def parse_login_page(html: str) -> dict[str, str]:
        patterns = {
            "randomvalue": r"var\s+randomvalue\s*=\s*'([^']+)'",
            "modulus": r"var\s+modulus\s*=\s*'([^']+)'",
            "exponent": r"var\s+exponent\s*=\s*'([^']+)'",
        }
        result: dict[str, str] = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, html)
            if not match:
                raise AuthenticationError(f"无法从登录页提取参数: {key}")
            result[key] = match.group(1)
        return result

    def build_form_data(self, params: dict[str, str]) -> dict[str, str]:
        password = self.config.password
        tokeninfo = f"{rsa_encrypt(password, params['modulus'], params['exponent'])}_encrypted"
        return {
            "yhtCountry": self.config.country,
            "username": self.config.username,
            "ssoLoginType": self.config.login_type,
            "tenantid": self.config.tenantid,
            "lt": "",
            "execution": "",
            "_eventId": "submit",
            "realusername": "",
            "tokeninfo": tokeninfo,
            "isAutoLogin": "0",
            "randomvalue": params["randomvalue"],
            "yhtPd1": sha1_hash(password),
            "yhtPd2": sha256_hash(password),
            "yhtPd3": md5_hash(password),
            "X-XSRF-TOKEN": "",
            "timeCode": "",
            "finger": self.config.finger,
            "encryptData": "",
            "sid": "",
            "beat": "",
            "topService": self.config.base_url + "/",
            "real": "",
            "validateCode": "",
            "validateKey": str(random.randint(10**15, 10**16 - 1)),
            "tenantPswIsSuccess": "true",
        }

    def _handle_login_html(self, session: requests.Session, html: str, posting_url: str = "") -> None:
        ticket_url = _extract_ticket_redirect(html)
        if ticket_url:
            if ticket_url.startswith("/"):
                ticket_url = self._cas_url(posting_url or self.build_login_url(), ticket_url)
            session.get(ticket_url, allow_redirects=True, timeout=20)
            return

        if "密码已过期" in html:
            raise PasswordExpiredError("账号密码已过期")
        if "用户名或密码错误" in html:
            raise AuthenticationError("用户名或密码错误")
        tfa = _detect_tfa_page(html)
        if tfa:
            self._complete_sms_login(session, tfa, posting_url)
            return
        raise AuthenticationError("登录返回 200，但未检测到成功跳转")

    def _complete_sms_login(self, session: requests.Session, tfa: dict[str, Any], posting_url: str) -> None:
        sms_code = self.config.sms_verify_code
        if not sms_code:
            raise SmsVerificationError(
                "检测到短信多因子验证，但该环境未启用自动短信流程（sms_verify_code 为空）；"
                "如需自动登录，请在环境配置中设置 sms_verify_code"
            )
        if not tfa.get("mobile_available", True):
            raise SmsVerificationError("仅支持手机短信多因子验证，当前环境只提供了邮箱等其他验证方式")
        posting_url = posting_url or self.build_login_url()
        if not _same_https_origin(posting_url, self.config.base_url):
            raise SmsVerificationError("短信验证入口必须是同源 HTTPS 地址")
        try:
            self._send_sms_code(session, posting_url, tfa["tfa_id"])
        except CaptchaError as exc:
            raise SmsVerificationError(str(exc)) from None
        tfa_login_url = urlsplit(posting_url)._replace(path="/cas/tfaLogin").geturl()
        form = {
            "tfaValidateCode": sms_code,
            "tfaType": "mobile",
            "currentTfaWay": "normal",
            "X-XSRF-TOKEN": "",
            "finger": "",
            "topService": "",
            "real": "",
            "tfaId": tfa["tfa_id"],
            "validateCode": "",
            "validateKey": "false",
            "mfaCodeInput": "",
        }
        response = _sms_request(session, "post", tfa_login_url, data=form)
        ticket_url = response.headers.get("Location", "") if response.status_code in (301, 302, 303, 307, 308) else _extract_ticket_redirect(response.text)
        if ticket_url:
            self._follow_sms_ticket(session, posting_url, ticket_url)
            return
        raise SmsVerificationError("短信验证失败，未检测到成功跳转；请检查 sms_verify_code 配置（不会重新发码）")

    def _follow_sms_ticket(self, session, posting_url, ticket_url):
        # Follow bounded, same-origin redirects without leaking a ticket to another host.
        url = urljoin(posting_url, ticket_url)
        for _ in range(10):
            if not _same_https_origin(url, self.config.base_url):
                raise SmsVerificationError("短信认证跳转必须是同源 HTTPS 地址")
            response = _sms_request(session, "get", url)
            if response.status_code == 200:
                if _detect_tfa_page(response.text) or re.search(r"var\s+randomvalue\s*=", response.text):
                    raise SmsVerificationError("短信验证后仍要求登录")
                return
            location = response.headers.get("Location")
            if not location:
                break
            url = urljoin(url, location)
        raise SmsVerificationError("短信认证跳转未完成")

    def _send_sms_code(self, session: requests.Session, posting_url: str, tfa_id: str) -> None:
        recognize = captcha_classifier()  # Resolve/install before fetching an expiring image.
        captcha_errors = 0
        waited = False
        for _ in range(4):
            attempt = self._try_send_sms(session, posting_url, tfa_id, recognize)
            reason = _sms_send_result(attempt)
            if reason == "success":
                return
            if reason == "captcha":
                captcha_errors += 1
                if captcha_errors < 3:
                    continue
                raise SmsVerificationError("图形验证码识别失败（已尝试 3 次）")
            if reason == "minute" and not waited:
                waited = True
                _sms_retry_wait(70)
                continue
            messages = {
                "minute": "短信发送被限流：分钟冷却后仍无法发送",
                "five_minutes": "短信发送被限流：5 分钟配额已用完，请稍后重试",
                "day": "短信发送被限流：24 小时配额已用完，请待配额恢复后重试",
            }
            raise SmsVerificationError(messages.get(reason, "短信发送失败：服务端拒绝或返回无法识别的结果"))
        raise SmsVerificationError("短信发送尝试已达上限")

    def _try_send_sms(self, session, posting_url, tfa_id, recognize) -> dict[str, Any]:
        key = str(time.time_ns() // 1_000_000)
        response = _sms_request(session, "get", self._cas_url(posting_url, "/cas/images/getValiImage"), params={"ts": key})
        if response.status_code != 200 or not response.content.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a")):
            raise SmsVerificationError("验证码图片响应无效")
        code = recognize(response.content)
        if not re.fullmatch(r"[A-Za-z0-9]{4}", code):
            return {"status": 0, "codemsg": "codeError"}
        response = _sms_request(
            session, "post", self._cas_url(posting_url, "/cas/sendTfaCode"),
            data={"key": key, "code": code, "tfaType": "mobile", "locale": "zh_CN", "tfaId": tfa_id},
        )
        if response.status_code != 200:
            raise SmsVerificationError("短信发送响应状态异常")
        try:
            result = response.json()
        except ValueError:
            raise SmsVerificationError("短信发送响应不是有效 JSON") from None
        if not isinstance(result, dict):
            raise SmsVerificationError("短信发送响应结构无效")
        return result

    def _cas_url(self, posting_url: str, path: str) -> str:
        parts = urlsplit(posting_url)
        return f"{parts.scheme}://{parts.netloc}{path}"


def _extract_ticket_redirect(html: str) -> str | None:
    for pattern in (
        r'window\.location\s*=\s*["\']([^"\']*ticket=[^"\']*)["\']',
        r'location\.href\s*=\s*["\']([^"\']*ticket=[^"\']*)["\']',
    ):
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _detect_tfa_page(html: str) -> dict[str, Any] | None:
    if "getValiImage" not in html or "sendTfaCode" not in html:
        return None
    match = re.search(r"var\s+tfaId\s*=\s*'([^']+)'", html)
    if not match:
        return None
    return {
        "tfa_id": match.group(1),
        "mobile_available": bool(re.search(r"var\s+tfaMobile\s*=\s*[\"']([^\"']+)[\"']", html)),
    }


def _sms_send_result(result: dict[str, Any]) -> str:
    message = " ".join(str(result.get(k) or "") for k in ("codemsg", "msg")).lower()
    # Long limits take priority; their messages also contain "分钟" or "sendmore".
    if "sendmore2" in message or "24小时" in message or "24 小时" in message:
        return "day"
    if "sendmore5min" in message or re.search(r"5\s*分钟", message):
        return "five_minutes"
    if "sendmore1" in message or re.search(r"(?<![0-9])1\s*分钟", message):
        return "minute"
    if any(str(result.get(k) or "").lower() == "codeerror" for k in ("codemsg", "msg")) or "图形验证码错误" in message:
        return "captcha"
    if type(result.get("status")) is int and result["status"] == 1 and "sendmore" not in message:
        return "success"
    return "unknown"


def _sms_request(session, method, url, **kwargs):
    try:
        response = getattr(session, method)(url, allow_redirects=False, timeout=20, **kwargs)
    except requests.RequestException:
        raise SmsVerificationError("短信认证请求失败，请检查网络后重试") from None
    if response.status_code not in {200, 301, 302, 303, 307, 308}:
        raise SmsVerificationError(f"短信认证请求失败：HTTP {response.status_code}")
    return response


def _sms_retry_wait(seconds: float) -> None:
    print(f"短信发送触发分钟限流，等待 {seconds:g} 秒后重试一次。", file=sys.stderr, flush=True)
    time.sleep(seconds)


def _prepare_session(session: requests.Session) -> requests.Session:
    session.trust_env = False
    raw_request = getattr(session, "request", None)
    if callable(raw_request):

        def request_without_sslkeylogfile(method: str, url: str, **kwargs: Any):
            with temporarily_disable_sslkeylogfile():
                return raw_request(method, url, **kwargs)

        session.request = request_without_sslkeylogfile  # type: ignore[method-assign]
    return session


def _same_https_origin(left: str, right: str) -> bool:
    try:
        left_url = urlparse(left)
        right_url = urlparse(right)
        return (
            left_url.scheme.lower() == right_url.scheme.lower() == "https"
            and left_url.hostname == right_url.hostname
            and (left_url.port or 443) == (right_url.port or 443)
            and left_url.username is None
            and left_url.password is None
        )
    except ValueError:
        return False


def sha1_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def sha256_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def md5_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def rsa_encrypt(password: str, modulus_hex: str, exponent_hex: str) -> str:
    modulus = int(modulus_hex, 16)
    exponent = int(exponent_hex, 16)
    message = int.from_bytes(password.encode("utf-8"), "big")
    encrypted = pow(message, exponent, modulus)
    width = max(2, len(modulus_hex))
    return format(encrypted, f"0{width}x")


@contextmanager
def temporarily_disable_sslkeylogfile():
    original = os.environ.pop("SSLKEYLOGFILE", None)
    try:
        yield
    finally:
        if original is not None:
            os.environ["SSLKEYLOGFILE"] = original
