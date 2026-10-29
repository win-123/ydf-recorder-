from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests

from .config import EnvironmentConfig


ORG_ID_KEYS = ("id", "orgId", "org_id", "pkOrg", "pk_org", "value", "key")
ORG_CODE_KEYS = (
    "code",
    "sourceCode",
    "orgCode",
    "org_code",
    "agencyCode",
    "agency_code",
    "unitCode",
    "unit_code",
    "refcode",
    "orgNo",
    "org_no",
)
ORG_NAME_KEYS = ("name", "orgName", "org_name", "label", "title", "refname")
CHILD_KEYS = ("children", "childrens", "items", "data", "rows")


@dataclass(slots=True)
class OrgMatch:
    org_id: str
    code: str
    name: str
    raw: dict[str, Any]


class DefaultOrgContext:
    def __init__(self, config: EnvironmentConfig, session: requests.Session) -> None:
        self.config = config
        self.session = session

    def apply(self, override: str | None = None) -> OrgMatch | None:
        criteria = _build_org_criteria(self.config, override)
        if not any(criteria.values()):
            return None
        payload = self.fetch_org_tree()
        match = find_org(payload, **criteria)
        if match is None:
            expected = criteria["org_id"] or criteria["code"] or criteria["name"]
            raise RuntimeError(f"未找到默认组织: {expected}")
        self.update_default_org(match.org_id)
        return match

    def fetch_org_tree(self) -> Any:
        response = self.session.post(urljoin(self.config.base_url, self.config.endpoints.org_tree), json={}, timeout=20)
        response.raise_for_status()
        payload = response.json()
        return payload.get("data") or payload.get("datas") or payload

    def update_default_org(self, org_id: str) -> None:
        response = self.session.post(
            urljoin(self.config.base_url, self.config.endpoints.update_default_org),
            json={"defaultOrg": org_id},
            timeout=20,
        )
        response.raise_for_status()
        payload = _safe_json(response)
        if isinstance(payload, dict) and payload.get("success") is False:
            raise RuntimeError(f"设置默认组织失败: {payload}")


def find_org(payload: Any, *, org_id: str = "", code: str = "", name: str = "") -> OrgMatch | None:
    for node in _walk_org_nodes(payload):
        node_id = _first_value(node, ORG_ID_KEYS)
        node_code = _first_value(node, ORG_CODE_KEYS)
        node_name = _first_value(node, ORG_NAME_KEYS)
        if org_id and node_id == org_id:
            return OrgMatch(org_id=node_id, code=node_code, name=node_name, raw=node)
        if code and (_matches_org_code(node_code, code) or _label_starts_with_code(node_name, code)):
            return OrgMatch(org_id=node_id, code=node_code, name=node_name, raw=node)
        if name and node_name == name:
            return OrgMatch(org_id=node_id, code=node_code, name=node_name, raw=node)
    return None


def _build_org_criteria(config: EnvironmentConfig, override: str | None) -> dict[str, str]:
    if override:
        return {"org_id": "", "code": override.strip(), "name": override.strip()}
    return {"org_id": "", "code": "", "name": ""}


def _walk_org_nodes(payload: Any):
    if isinstance(payload, dict):
        if _looks_like_org(payload):
            yield payload
        for key in CHILD_KEYS:
            children = payload.get(key)
            if children is not None:
                yield from _walk_org_nodes(children)
        return
    if isinstance(payload, list):
        for item in payload:
            yield from _walk_org_nodes(item)


def _looks_like_org(node: dict[str, Any]) -> bool:
    return any(key in node for key in (*ORG_ID_KEYS, *ORG_CODE_KEYS, *ORG_NAME_KEYS))


def _first_value(node: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = node.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _label_starts_with_code(label: str, code: str) -> bool:
    return label == code or label.startswith(f"{code} ") or label.startswith(f"{code}-")


def _matches_org_code(node_code: str, expected: str) -> bool:
    return node_code == expected or node_code.endswith(f"-{expected}")


def _safe_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return None
