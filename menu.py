"""菜单路径解析（正向：menu_path → service_code）。

与 ydf-browser 的 ``gateway.resolve_menu`` 对齐，但**不 import 任何
ydf_browser 模块**。调用方负责拉取菜单树 JSON 后传入（或使用本模块提供的
``fetch_menu_tree`` 辅助函数）。

反向解析（serviceCode → 中文路径）复用 ``menu_resolver``。
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests

from .config import RecorderEnv
from .menu_resolver import _walk_menu_tree


def resolve_menu_to_service_code(
    payload: Any,
    menu_path: str,
) -> str:
    """在菜单树中查找 menu_path 对应的 serviceCode。

    Args:
        payload: service_tree 接口的原始返回（``{"data": [...]}`` 或列表）。
        menu_path: 中文菜单路径，用 ``>>`` 分隔（如 ``"项目库>>项目建议>>项目建议"``）。

    Returns:
        serviceCode 字符串。

    Raises:
        ValueError: 菜单路径为空、未找到或找到多个匹配。
    """
    path_parts = [part.strip() for part in menu_path.split(">>") if part.strip()]
    if not path_parts:
        raise ValueError("菜单路径不能为空")

    tree = _unwrap_payload(payload)
    matches = [
        (node, path)
        for node, path in _walk_menu_tree(tree, [])
        if _match_path(path, path_parts)
    ]
    if not matches:
        _all = [">>".join(_p) for _, _p in _walk_menu_tree(tree, [])]
        raise ValueError(f"未找到菜单: {menu_path} | 菜单树共{len(_all)}个节点, 前10条: {_all[:10]}")
    if len(matches) > 1:
        raise ValueError(f"找到多个菜单，无法唯一定位: {menu_path}")

    node = matches[0][0]
    service_code = str(node.get("serviceCode") or "").strip()
    if not service_code:
        raise ValueError(f"菜单 '{menu_path}' 没有 serviceCode")
    return service_code


def fetch_menu_tree(env: RecorderEnv, session: requests.Session) -> Any:
    """通过 service_tree 端点拉取菜单树 JSON。"""
    url = urljoin(env.base_url, env.endpoints.service_tree)
    response = session.get(url, timeout=20)
    response.raise_for_status()
    return response.json()


def build_service_url(base_url: str, service_code: str) -> str:
    """构建菜单打开 URL（与 ydf-browser 的 build_service_url 对齐）。"""
    return f"{base_url.rstrip('/')}/#/service/{service_code}"


# ── 内部函数 ──────────────────────────────────────────────


def _unwrap_payload(payload: Any) -> Any:
    """service_tree 返回可能是 {data: [...]} / {datas: [...]} / 裸列表，统一取出树体。"""
    if isinstance(payload, dict):
        for key in ("data", "datas"):
            value = payload.get(key)
            if value:
                return value
    return payload


def _match_path(candidate_path: list[str], target_path: list[str]) -> bool:
    """后缀匹配：候选路径末尾匹配目标路径。"""
    if len(candidate_path) < len(target_path):
        return False
    return candidate_path[-len(target_path):] == target_path
