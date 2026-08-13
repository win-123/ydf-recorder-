"""CAS 认证与上下文切换（与 ydf-browser 解耦）。

复刻 ydf-browser 的登录链路（``auth.py`` + ``tenant_context.py`` +
``org_context.py`` + ``fiscal_year_context.py``），但**不 import 任何
ydf_browser 模块**。返回的 ``requests.Session`` 携带登录后的 cookies，
调用方负责将其注入 Playwright 浏览器上下文。

流程：
  1. CAS 登录（RSA 加密密码 → POST 表单 → 跟随重定向）
  2. 租户切换（可选）
  3. 默认组织切换（可选）
  4. 业务年度切换（可选）
"""

from __future__ import annotations

import hashlib
import os
import random
import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode, urljoin, urlparse

import requests

from .config import RecorderEnv


class AuthenticationError(RuntimeError):
    """CAS 登录失败。"""


class PasswordExpiredError(AuthenticationError):
    """账号密码已过期。"""


@dataclass(slots=True)
class LoginResult:
    """登录结果：session + 上下文切换信息。"""

    session: requests.Session
    tenant_id: str = ""
    tenant_name: str = ""
    org_id: str = ""
    org_code: str = ""
    org_name: str = ""
    fiscal_year: str = ""


# ── CAS 登录 ──────────────────────────────────────────────


def login(env: RecorderEnv) -> LoginResult:
    """执行 CAS 登录，返回携带 cookies 的 session。

    Args:
        env: 环境配置（需含 base_url/username/password）。

    Raises:
        AuthenticationError: 登录失败。
        PasswordExpiredError: 密码已过期。
    """
    if not env.username or not env.password:
        raise AuthenticationError(
            "缺少用户名或密码，请在 env.yaml 中配置 username/password 或 users 别名"
        )

    session = _prepare_session(requests.Session())
    session.cookies.clear()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        }
    )

    login_url = _build_login_url(env)
    with _temporarily_disable_sslkeylogfile():
        page = session.get(login_url, timeout=20)
        page.raise_for_status()
        params = _parse_login_page(page.text)
        form_data = _build_form_data(env, params)
        response = session.post(login_url, data=form_data, allow_redirects=False, timeout=20)

        if response.status_code in (301, 302, 303, 307):
            location = response.headers.get("Location", "")
            if location.startswith("/"):
                location = f"{env.base_url}{location}"
            if location:
                session.get(location, allow_redirects=True, timeout=20)
        elif response.status_code == 200:
            _handle_login_html(env, session, response.text)
        else:
            raise AuthenticationError(f"登录失败，状态码: {response.status_code}")

    return LoginResult(session=session)


def _build_login_url(env: RecorderEnv) -> str:
    service_url = (
        f"{env.base_url}/login_light"
        f"?yhtdesturl=/yhtssoislogin"
        f"&finger={env.finger}"
        f"&yhtrealservice={env.base_url}"
    )
    return (
        f"{env.base_url}/cas/login"
        f"?sysid={env.sysid}"
        f"&mode=light"
        f"&casLoginType=normal"
        f"&themeColor="
        f"&service={quote(service_url, safe='')}"
        f"&locale=zh_CN"
    )


def _parse_login_page(html: str) -> dict[str, str]:
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


def _build_form_data(env: RecorderEnv, params: dict[str, str]) -> dict[str, str]:
    password = env.password
    tokeninfo = f"{_rsa_encrypt(password, params['modulus'], params['exponent'])}_encrypted"
    return {
        "yhtCountry": env.country,
        "username": env.username,
        "ssoLoginType": env.login_type,
        "tenantid": env.tenantid,
        "lt": "",
        "execution": "",
        "_eventId": "submit",
        "realusername": "",
        "tokeninfo": tokeninfo,
        "isAutoLogin": "0",
        "randomvalue": params["randomvalue"],
        "yhtPd1": _sha1_hash(password),
        "yhtPd2": _sha256_hash(password),
        "yhtPd3": _md5_hash(password),
        "X-XSRF-TOKEN": "",
        "timeCode": "",
        "finger": env.finger,
        "encryptData": "",
        "sid": "",
        "beat": "",
        "topService": env.base_url + "/",
        "real": "",
        "validateCode": "",
        "validateKey": str(random.randint(10**15, 10**16 - 1)),
        "tenantPswIsSuccess": "true",
    }


def _handle_login_html(env: RecorderEnv, session: requests.Session, html: str) -> None:
    redirect_patterns = [
        r'window\.location\s*=\s*["\']([^"\']*ticket=[^"\']*)["\']',
        r'location\.href\s*=\s*["\']([^"\']*ticket=[^"\']*)["\']',
    ]
    for pattern in redirect_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            redirect_url = match.group(1)
            if redirect_url.startswith("/"):
                redirect_url = f"{env.base_url}{redirect_url}"
            session.get(redirect_url, allow_redirects=True, timeout=20)
            return

    if "密码已过期" in html:
        raise PasswordExpiredError("账号密码已过期")
    if "用户名或密码错误" in html:
        raise AuthenticationError("用户名或密码错误")
    raise AuthenticationError("登录返回 200，但未检测到成功跳转")


# ── 上下文切换 ─────────────────────────────────────────────


def apply_context(
    env: RecorderEnv,
    result: LoginResult,
    *,
    tenant_name: str = "",
    default_org: str = "",
    fiscal_year: str = "",
) -> LoginResult:
    """登录后切换租户/组织/业务年度上下文。

    按需切换：仅在参数非空时执行对应步骤。
    切换租户/组织后需要重新登录以刷新 session。

    Args:
        env: 环境配置。
        result: 登录结果（会被更新）。
        tenant_name: 租户名称（如 "财政一体化"）。
        default_org: 默认组织编码（如 "049002"）。
        fiscal_year: 业务年度（如 "2027"）。

    Returns:
        更新后的 LoginResult（可能包含新的 session）。
    """
    session = result.session
    tenant_id = ""
    org_id = ""

    # 1. 租户切换
    if tenant_name:
        tenant_id = _switch_tenant(env, session, tenant_name)
        result.tenant_id = tenant_id
        result.tenant_name = tenant_name

    # 2. 默认组织切换
    if default_org:
        org_id = _switch_default_org(env, session, default_org)
        result.org_id = org_id
        result.org_code = default_org

    # 3. 如果切换了租户或组织，需要重新登录刷新 session
    if tenant_name or default_org:
        relogin = login(env)
        result.session = relogin.session

    # 4. 业务年度切换
    if fiscal_year:
        _switch_fiscal_year(env, result.session, fiscal_year)
        result.fiscal_year = fiscal_year

    return result


def _switch_tenant(env: RecorderEnv, session: requests.Session, tenant_name: str) -> str:
    """切换租户，返回 tenant_id。"""
    payload = _fetch_json(session, urljoin(env.base_url, env.endpoints.tenant_information))
    tenant_id = _find_tenant_id(payload, tenant_name)
    if not tenant_id:
        raise RuntimeError(f"未找到租户: {tenant_name}")

    query = urlencode(
        {
            "tenantId": tenant_id,
            "dimension": tenant_id,
            "switch": "true",
            "finger": env.finger,
        }
    )
    url = f"{urljoin(env.base_url, env.endpoints.switch_tenant)}?{query}"
    response = session.get(url, timeout=20)
    response.raise_for_status()
    data = _safe_json(response)
    if isinstance(data, dict) and data.get("success") is False:
        raise RuntimeError(f"切换租户失败: {data}")
    return tenant_id


def _switch_default_org(env: RecorderEnv, session: requests.Session, org_code: str) -> str:
    """切换默认组织，返回 org_id。"""
    payload = _fetch_json_post(session, urljoin(env.base_url, env.endpoints.org_tree), json_body={})
    org_tree = payload.get("data") or payload.get("datas") or payload
    org_id = _find_org_id(org_tree, org_code)
    if not org_id:
        raise RuntimeError(f"未找到默认组织: {org_code}")

    response = session.post(
        urljoin(env.base_url, env.endpoints.update_default_org),
        json={"defaultOrg": org_id},
        timeout=20,
    )
    response.raise_for_status()
    data = _safe_json(response)
    if isinstance(data, dict) and data.get("success") is False:
        raise RuntimeError(f"设置默认组织失败: {data}")
    return org_id


def _switch_fiscal_year(env: RecorderEnv, session: requests.Session, fiscal_year: str) -> None:
    """切换业务年度。"""
    query = urlencode({"fiscalYear": fiscal_year})
    url = f"{urljoin(env.base_url, env.endpoints.switch_fiscal_year)}?{query}"
    response = session.get(url, timeout=20)
    response.raise_for_status()
    data = _safe_json(response)
    if isinstance(data, dict) and data.get("success") is False:
        raise RuntimeError(f"设置业务年度失败: {data}")


# ── Cookie 提取 ────────────────────────────────────────────


def cookies_for_playwright(env: RecorderEnv, session: requests.Session) -> list[dict[str, Any]]:
    """将 requests.Session 的 cookies 转换为 Playwright add_cookies 格式。"""
    parsed = urlparse(env.base_url)
    domain = parsed.hostname or ""
    cookies: list[dict[str, Any]] = []
    for cookie in session.cookies:
        entry: dict[str, Any] = {
            "name": cookie.name,
            "value": cookie.value,
            "domain": cookie.domain or domain,
            "path": cookie.path or "/",
            "secure": bool(cookie.secure),
        }
        if cookie.expires:
            entry["expires"] = float(cookie.expires)
        cookies.append(entry)
    return cookies


# ── 辅助函数 ──────────────────────────────────────────────


def _prepare_session(session: requests.Session) -> requests.Session:
    session.trust_env = False
    # ★ 与 ydf-browser 对齐：让 session 的每个请求都屏蔽 SSLKEYLOGFILE，
    # 避免某些 Windows 环境（Wireshark/Fiddler 等）导致 SSL 握手失败
    raw_request = getattr(session, "request", None)
    if callable(raw_request):

        def request_without_sslkeylogfile(method: str, url: str, **kwargs: Any):
            with _temporarily_disable_sslkeylogfile():
                return raw_request(method, url, **kwargs)

        session.request = request_without_sslkeylogfile  # type: ignore[method-assign]
    return session


def _fetch_json(session: requests.Session, url: str) -> Any:
    response = session.get(url, timeout=20)
    response.raise_for_status()
    return response.json()


def _fetch_json_post(session: requests.Session, url: str, json_body: dict) -> Any:
    response = session.post(url, json=json_body, timeout=20)
    response.raise_for_status()
    return response.json()


def _safe_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return None


def _find_tenant_id(payload: Any, name: str) -> str:
    """从租户列表中按名称查找 tenant_id。"""
    for node in _walk_tenant_nodes(payload):
        node_id = _first_value(node, ("tenantId", "tenant_id", "id", "value", "key"))
        node_name = _first_value(node, ("tenantName", "tenant_name", "name", "label", "title"))
        if name and node_name == name:
            return node_id
    return ""


def _walk_tenant_nodes(payload: Any):
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("tenants"), list):
            for item in data["tenants"]:
                if isinstance(item, dict):
                    yield item
            return
        tenants = payload.get("tenants")
        if isinstance(tenants, list):
            for item in tenants:
                if isinstance(item, dict):
                    yield item
            return
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield ite# --- org tree (aligned with ydf-browser org_context.py) ---
_ORG_ID_KEYS = ("id", "orgId", "org_id", "pkOrg", "pk_org", "value", "key")
_ORG_CODE_KEYS = (
    "code", "sourceCode", "orgCode", "org_code", "agencyCode",
    "agency_code", "unitCode", "unit_code", "refcode", "orgNo", "org_no",
)
_ORG_NAME_KEYS = ("name", "orgName", "org_name", "label", "title", "refname")
_CHILD_KEYS = ("children", "childrens", "items", "data", "rows")


def _find_org_id(payload: Any, code: str) -> str:
    """Find org_id by code (aligned with ydf-browser find_org)."""
    for node in _walk_org_nodes(payload):
        node_id = _first_value(node, _ORG_ID_KEYS)
        node_code = _first_value(node, _ORG_CODE_KEYS)
        node_name = _first_value(node, _ORG_NAME_KEYS)
        if code and _matches_org_code(node_code, code):
            return node_id
        if code and _label_starts_with_code(node_name, code):
            return node_id
    return ""


def _walk_org_nodes(payload: Any):
    """Walk org tree, only yield dicts that look like org nodes."""
    if isinstance(payload, dict):
        if _looks_like_org(payload):
            yield payload
        for key in _CHILD_KEYS:
            children = payload.get(key)
            if children is not None:
                yield from _walk_org_nodes(children)
        return
    if isinstance(payload, list):
        for item in payload:
            yield from _walk_org_nodes(item)


def _looks_like_org(node: dict) -> bool:
    return any(key in node for key in (*_ORG_ID_KEYS, *_ORG_CODE_KEYS, *_ORG_NAME_KEYS))


def _label_starts_with_code(label: str, code: str) -> bool:
    return label == code or label.startswith(f"{code} ") or label.startswith(f"{code}-")


def _matches_org_code(node_code: str, expected: str) -> bool:
    return node_code == expected or node_code.endswith(f"-{expected}")


def _first_value(node: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = node.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _sha1_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _sha256_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _md5_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _rsa_encrypt(password: str, modulus_hex: str, exponent_hex: str) -> str:
    modulus = int(modulus_hex, 16)
    exponent = int(exponent_hex, 16)
    message = int.from_bytes(password.encode("utf-8"), "big")
    encrypted = pow(message, exponent, modulus)
    width = max(2, len(modulus_hex))
    return format(encrypted, f"0{width}x")


@contextmanager
def _temporarily_disable_sslkeylogfile():
    original = os.environ.pop("SSLKEYLOGFILE", None)
    try:
        yield
    finally:
        if original is not None:
            os.environ["SSLKEYLOGFILE"] = original
