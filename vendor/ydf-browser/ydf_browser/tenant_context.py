from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit

import requests

from .config import EnvironmentConfig
from .auth import SessionExpired


TENANT_ID_KEYS = ("tenantId", "tenant_id", "id", "value", "key")
TENANT_NAME_KEYS = ("tenantName", "tenant_name", "name", "label", "title")


@dataclass(slots=True)
class TenantMatch:
    tenant_id: str
    tenant_name: str
    raw: dict[str, Any]


class TenantContext:
    def __init__(self, config: EnvironmentConfig, session: requests.Session) -> None:
        self.config = config
        self.session = session

    def apply(self, tenant_name: str | None = None) -> TenantMatch | None:
        name = str(tenant_name or "").strip()
        if not name:
            return None
        payload = self.fetch_tenants()
        match = find_tenant(payload, name=name)
        if match is None:
            raise RuntimeError(f"未找到租户: {name}")
        self.switch_tenant(match.tenant_id)
        return match

    def fetch_tenants(self) -> Any:
        response = self.session.get(
            urljoin(self.config.base_url, self.config.endpoints.tenant_information),
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def switch_tenant(self, tenant_id: str) -> None:
        query = urlencode(
            {
                "tenantId": tenant_id,
                "dimension": tenant_id,
                "switch": "true",
                "finger": self.config.finger,
            }
        )
        url = f"{urljoin(self.config.base_url, self.config.endpoints.switch_tenant)}?{query}"
        response = self.session.get(url, timeout=20)
        if (getattr(response, "status_code", None) == 401
                or urlsplit(str(getattr(response, "url", "") or "")).path == "/cas/login"):
            raise SessionExpired("上下文刷新要求重新认证")
        response.raise_for_status()
        payload = _safe_json(response)
        if isinstance(payload, dict) and payload.get("success") is False:
            raise RuntimeError(f"切换租户失败: {payload}")


class UserContextVerifier:
    def __init__(self, config: EnvironmentConfig, session: requests.Session) -> None:
        self.config = config
        self.session = session

    def verify(self, *, expected_tenant_id: str = "", expected_org_id: str = "") -> dict[str, Any]:
        if not expected_tenant_id and not expected_org_id:
            return {}
        context = self.fetch_user_context()
        actual_tenant_id = str(context.get("tenantId") or "")
        actual_org_id = str(context.get("defaultOrg") or "")
        if expected_tenant_id and actual_tenant_id != expected_tenant_id:
            raise RuntimeError(f"当前租户不匹配: expected={expected_tenant_id}, actual={actual_tenant_id}")
        if expected_org_id and actual_org_id != expected_org_id:
            raise RuntimeError(f"当前组织不匹配: expected={expected_org_id}, actual={actual_org_id}")
        return context

    def fetch_user_context(self) -> dict[str, Any]:
        response = self.session.get(
            urljoin(self.config.base_url, self.config.endpoints.user_context),
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise RuntimeError(f"获取当前上下文失败: {payload}")
        return data


def find_tenant(payload: Any, *, name: str = "", tenant_id: str = "") -> TenantMatch | None:
    for node in _walk_tenant_nodes(payload):
        node_id = _first_value(node, TENANT_ID_KEYS)
        node_name = _first_value(node, TENANT_NAME_KEYS)
        if tenant_id and node_id == tenant_id:
            return TenantMatch(tenant_id=node_id, tenant_name=node_name, raw=node)
        if name and node_name == name:
            return TenantMatch(tenant_id=node_id, tenant_name=node_name, raw=node)
    return None


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
                yield item


def _first_value(node: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = node.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _safe_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return None
