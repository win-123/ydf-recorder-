from __future__ import annotations

import time
from collections.abc import Iterable
from urllib.parse import parse_qs, urljoin, urlsplit

import requests

from .config import EnvironmentConfig
from .models import MenuTarget

__all__ = [
    "MenuTarget",
    "YondifGateway",
    "extract_template_context",
    "parse_service_detail",
    "resolve_menu_from_tree",
]


class YondifGateway:
    def __init__(self, config: EnvironmentConfig, session: requests.Session) -> None:
        self.config = config
        self.session = session

    def resolve_menu(self, menu_path: str, timeout_seconds: float | None = None) -> MenuTarget:
        response = self.session.get(
            urljoin(self.config.base_url, self.config.endpoints.service_tree),
            timeout=min(20, timeout_seconds) if timeout_seconds is not None else 20,
        )
        response.raise_for_status()
        payload = response.json()
        tree = payload.get("data") or payload.get("datas") or payload
        return resolve_menu_from_tree(tree, menu_path)

    def fetch_service_detail(self, service_code: str, timeout_seconds: float | None = None) -> dict[str, str]:
        response = self.session.get(
            urljoin(
                self.config.base_url,
                f"{self.config.endpoints.service_detail}?serviceCode={service_code}",
            ),
            timeout=min(20, timeout_seconds) if timeout_seconds is not None else 20,
        )
        response.raise_for_status()
        return parse_service_detail(response.json(), service_code)

    def fetch_template(self, menu_target: MenuTarget, timeout_seconds: float | None = None) -> dict:
        deadline = time.monotonic() + timeout_seconds if timeout_seconds is not None else None
        service_detail = self.fetch_service_detail(
            menu_target.service_code or "",
            timeout_seconds=_remaining_timeout(deadline),
        )
        menu_target.service_url = service_detail["service_url"]
        menu_target.native_url = service_detail["native_url"]
        menu_target.template_code = service_detail["code"]
        menu_target.transtype_code = service_detail["transtypeCode"]
        menu_target.business_step = service_detail["businessStep"]
        if service_detail["service_name"]:
            menu_target.raw = {**menu_target.raw, "serviceName": service_detail["service_name"]}
        template_response = self.session.post(
            urljoin(
                self.config.base_url,
                f"{self.config.endpoints.templates}?serviceCode={menu_target.service_code}",
            ),
            json={
                "serviceCode": menu_target.service_code,
                "code": service_detail["code"],
                "transtypeCode": service_detail["transtypeCode"],
                "businessStep": service_detail["businessStep"],
                "type": "pc",
            },
            timeout=min(20, _remaining_timeout(deadline)) if deadline is not None else 20,
        )
        template_response.raise_for_status()
        return template_response.json()


def resolve_menu_from_tree(menu_tree: object, menu_path: str) -> MenuTarget:
    path_parts = [part.strip() for part in menu_path.split(">>") if part.strip()]
    if not path_parts:
        raise ValueError("菜单路径不能为空")
    matches = [candidate for candidate in _walk_menu_tree(menu_tree, []) if _match_path(candidate["path"], path_parts)]
    if not matches:
        raise ValueError(f"未找到菜单: {menu_path}")
    if len(matches) > 1:
        candidates = "\n".join(
            f"- {'>>'.join(candidate['path'])} (serviceCode={candidate['node'].get('serviceCode') or ''})"
            for candidate in matches
        )
        raise ValueError(f"找到多个菜单，无法唯一定位: {menu_path}\n候选完整路径:\n{candidates}")
    match = matches[0]
    return MenuTarget(
        menu_code=str(
            match["node"].get("menuCode")
            or match["node"].get("menuItemId")
            or match["node"].get("code")
            or match["node"].get("id")
            or ""
        ),
        menu_name=str(match["node"].get("menuName") or match["node"].get("label") or path_parts[-1]),
        path=match["path"],
        service_code=match["node"].get("serviceCode"),
        page_code=match["node"].get("pageCode"),
        biz_obj_code=match["node"].get("bizObjCode"),
        page_id=match["node"].get("pageId"),
        raw=match["node"],
    )


def _walk_menu_tree(menu_tree: object, path: list[str]) -> Iterable[dict]:
    if isinstance(menu_tree, dict):
        node = menu_tree
        label = _extract_menu_label(node)
        next_path = path + [label] if label else path
        if label:
            yield {"node": node, "path": next_path}
        for child in _iter_children(node):
            yield from _walk_menu_tree(child, next_path)
        return
    if isinstance(menu_tree, list):
        for node in menu_tree:
            yield from _walk_menu_tree(node, path)


def _iter_children(node: dict) -> list[dict]:
    children = node.get("children") or node.get("childrens") or node.get("menuItems") or []
    return [child for child in children if isinstance(child, dict)]


def _extract_menu_label(node: dict) -> str:
    multi_lang = node.get("multiLangText") or node.get("menuBarMultiLangText") or {}
    if isinstance(multi_lang, dict):
        label = multi_lang.get("zh_CN") or multi_lang.get("en_US")
        if label:
            return str(label).strip()
    return str(
        node.get("menuName")
        or node.get("label")
        or node.get("name")
        or node.get("menuItemCode")
        or node.get("menuBarCode")
        or ""
    ).strip()


def _match_path(candidate_path: list[str], target_path: list[str]) -> bool:
    if len(candidate_path) < len(target_path):
        return False
    return candidate_path[-len(target_path) :] == target_path


def extract_template_context(service_payload: dict) -> dict[str, str]:
    data = service_payload.get("data") or {}
    native_url = data.get("nativeUrl") or data.get("url") or ""
    params = _extract_url_params(native_url)
    return {
        "code": _first_query_value(params, "code"),
        "transtypeCode": _first_query_value(params, "transtypeCode"),
        "businessStep": _first_query_value(params, "businessStep"),
    }


def parse_service_detail(service_payload: dict, fallback_service_code: str = "") -> dict[str, str]:
    data = service_payload.get("data") or {}
    context = extract_template_context(service_payload)
    native_url = data.get("nativeUrl") or ""
    return {
        "service_code": data.get("serviceCode") or fallback_service_code,
        "service_name": data.get("serviceName") or "",
        "service_url": data.get("url") or _derive_service_url_from_native_url(native_url),
        "native_url": native_url,
        "code": context["code"],
        "transtypeCode": context["transtypeCode"],
        "businessStep": context["businessStep"],
    }


def _extract_url_params(url: str) -> dict[str, list[str]]:
    split = urlsplit(url)
    params = parse_qs(split.query, keep_blank_values=True)
    fragment = split.fragment or ""
    if "?" not in fragment:
        return params
    fragment_query = fragment.split("?", 1)[1]
    fragment_params = parse_qs(fragment_query, keep_blank_values=True)
    for key, values in fragment_params.items():
        if not _first_query_value(params, key):
            params[key] = values
    return params


def _first_query_value(params: dict[str, list[str]], key: str) -> str:
    values = params.get(key)
    if not values:
        return ""
    return values[0] or ""


def _derive_service_url_from_native_url(native_url: str) -> str:
    if native_url.startswith("tns:///"):
        return f"#/{native_url.removeprefix('tns:///')}"
    return native_url


def _remaining_timeout(deadline: float | None) -> float | None:
    return None if deadline is None else max(deadline - time.monotonic(), 0.001)
