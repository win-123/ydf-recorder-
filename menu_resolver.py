"""菜单路径反查器（serviceCode → 中文 ``>>`` 路径）。

录制时只能从 URL 拿到 serviceCode，但 DSL 的 ``open_menu`` 需要中文菜单路径
（``ydf_browser.gateway.resolve_menu`` 按 ``>>`` 标签路径解析）。本模块把
service_tree 接口返回的菜单树反查为中文路径。

纯函数，不依赖网络/playwright：调用方负责拉取菜单树 JSON 后传入。遍历逻辑
对齐 ``ydf_browser.gateway``（``serviceCode`` 字段、``multiLangText`` 标签、
``children/childrens/menuItems`` 子节点），但**不 import ydf_browser**。
"""

from __future__ import annotations

from typing import Any, Iterator


def resolve_menu_path_from_tree(payload: Any, service_code: str) -> str | None:
    """在菜单树中查找 serviceCode 对应节点的中文 ``>>`` 路径。

    Args:
        payload: service_tree 接口的原始返回（``{"data": [...]}`` 或列表）。
        service_code: 目标 serviceCode。

    Returns:
        形如 ``"合同管理>>付款合同>>付款合同登记"`` 的路径；未找到返回 None。
    """
    if not service_code:
        return None
    tree = _unwrap_payload(payload)
    for node, path in _walk_menu_tree(tree, []):
        if str((node or {}).get("serviceCode") or "") == service_code:
            return ">>".join(path) if path else None
    return None


def _unwrap_payload(payload: Any) -> Any:
    """service_tree 返回可能是 {data: [...]} / {datas: [...]} / 裸列表，统一取出树体。"""
    if isinstance(payload, dict):
        for key in ("data", "datas"):
            value = payload.get(key)
            if value:
                return value
    return payload


def _walk_menu_tree(node: Any, path: list[str]) -> Iterator[tuple[dict, list[str]]]:
    """深度遍历菜单树，yield (node, 中文标签路径)。"""
    if isinstance(node, dict):
        label = _extract_menu_label(node)
        next_path = path + [label] if label else path
        if label:
            yield node, next_path
        for child in _iter_children(node):
            yield from _walk_menu_tree(child, next_path)
        return
    if isinstance(node, list):
        for item in node:
            yield from _walk_menu_tree(item, path)


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
