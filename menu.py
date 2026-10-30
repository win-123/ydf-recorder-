"""菜单路径解析（正向：menu_path → service_code）。

与 ydf-browser 的 ``gateway.resolve_menu`` 对齐，但**不 import 任何
ydf_browser 模块**。调用方负责拉取菜单树 JSON 后传入（或使用本模块提供的
``fetch_menu_tree`` 辅助函数）。

反向解析（serviceCode → 中文路径）复用 ``menu_resolver``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests

from .config import RecorderEnv
from .menu_resolver import _walk_menu_tree


@dataclass(frozen=True)
class MenuResolution:
    """菜单解析结果。

    ``path`` 是**菜单树里的完整路径**（``>>`` 分隔），与
    ``ydf_browser.gateway.resolve_menu`` 的后缀精确匹配完全对齐。
    录制/回放都必须把这条路径写进 DSL：用户手填的路径常缺层级
    （如漏掉「一级项目」），回放端是精确匹配，会直接报「未找到菜单」。
    """

    service_code: str
    path: str
    matched_by: str = "exact"  # exact / raw_leaf / normalized_leaf / contains


def resolve_menu_target(payload: Any, menu_path: str) -> MenuResolution:
    """在菜单树中查找 menu_path 对应的 serviceCode 与规范路径。

    Raises:
        ValueError: 菜单路径为空、未找到或找到多个匹配。
    """
    path_parts = [part.strip() for part in menu_path.split(">>") if part.strip()]
    if not path_parts:
        raise ValueError("菜单路径不能为空")

    tree = _unwrap_payload(payload)
    matched_by = "exact"
    matches = [
        (node, path)
        for node, path in _walk_menu_tree(tree, [])
        if _match_path(path, path_parts)
    ]
    if not matches:
        # 精确后缀匹配失败 → 模糊兜底（按优先级）：
        #   L0 叶子名原始值完全相等（保留「（财政）」等括号后缀区分）
        #   L1 叶子名归一化相等（去空白/括号后缀/大小写）
        #   L2 叶子名双向包含（适配环境间菜单改名/层级差异）
        raw_leaf = path_parts[-1].strip()
        leaf = _normalize_leaf(path_parts[-1])
        all_paths = [(node, path) for node, path in _walk_menu_tree(tree, []) if path]
        l0 = [(n, p) for n, p in all_paths if p[-1].strip() == raw_leaf]
        l1 = [(n, p) for n, p in all_paths if not l0 and _normalize_leaf(p[-1]) == leaf]
        l2 = [
            (n, p)
            for n, p in all_paths
            if not l0 and not l1
            and _leaf_contains(_normalize_leaf(p[-1]), leaf)
        ]
        if l0:
            candidates, matched_by = l0, "raw_leaf"
        elif l1:
            candidates, matched_by = l1, "normalized_leaf"
        else:
            candidates, matched_by = l2, "contains"
        if len(candidates) == 1:
            matches = candidates
        elif len(candidates) > 1:
            shown = [">>".join(p) for _, p in candidates[:8]]
            raise ValueError(
                f"菜单模糊匹配到多个候选，请用完整路径精确指定: {menu_path} | 候选: {shown}"
            )
    if not matches:
        _all = [">>".join(_p) for _, _p in _walk_menu_tree(tree, [])]
        raise ValueError(f"未找到菜单: {menu_path} | 菜单树共{len(_all)}个节点, 前10条: {_all[:10]}")
    if len(matches) > 1:
        raise ValueError(f"找到多个菜单，无法唯一定位: {menu_path}")

    node, resolved_path = matches[0]
    service_code = str(node.get("serviceCode") or "").strip()
    if not service_code:
        raise ValueError(f"菜单 '{menu_path}' 没有 serviceCode")
    return MenuResolution(
        service_code=service_code,
        path=">>".join(resolved_path),
        matched_by=matched_by,
    )


def resolve_menu_to_service_code(
    payload: Any,
    menu_path: str,
) -> str:
    """在菜单树中查找 menu_path 对应的 serviceCode（``resolve_menu_target`` 的简写）。

    Args:
        payload: service_tree 接口的原始返回（``{"data": [...]}`` 或列表）。
        menu_path: 中文菜单路径，用 ``>>`` 分隔（如 ``"项目库>>项目建议>>项目建议"``）。

    Returns:
        serviceCode 字符串。

    Raises:
        ValueError: 菜单路径为空、未找到或找到多个匹配。
    """
    return resolve_menu_target(payload, menu_path).service_code


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


def _normalize_leaf(name: str) -> str:
    """菜单名归一化：去空白、去括号后缀（如「（财政）」）、转小写。"""
    import re

    text = (name or "").strip()
    text = re.sub(r"[（(][^（()）]*[)）]\s*$", "", text)
    return text.strip().lower()


def _leaf_contains(candidate_leaf: str, target_leaf: str) -> bool:
    """双向包含判断（两端非空且互为子串）。"""
    if not candidate_leaf or not target_leaf:
        return False
    return candidate_leaf in target_leaf or target_leaf in candidate_leaf
