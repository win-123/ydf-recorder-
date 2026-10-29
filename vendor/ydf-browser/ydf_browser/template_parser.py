from __future__ import annotations

import re
from typing import Any

from .adapters import default_render_adapter_registry
from .models import ElementCandidate, PageManifest, PageMeta, Region, TemplateNode

RENDER_ADAPTERS = default_render_adapter_registry()

PRIORITY_MAP = {
    "step_bar": 10,
    "tab_bar": 15,
    "top_action_bar": 20,
    "query_box": 30,
    "main_table": 40,
    "table_action_bar": 50,
    "tree": 60,
    "dialog_page": 80,
    "content_card": 90,
    "page_root": 100,
}


def build_page_manifest(page_json: dict[str, Any]) -> PageManifest:
    data = page_json.get("data") or {}
    uidata = data.get("uidata") or []
    if not uidata or not isinstance(uidata[0], dict):
        raise ValueError("matchingTemplate 响应缺少 data.uidata[0]")

    root_node = uidata[0]
    manifest = PageManifest(
        page=PageMeta(
            fieldid=root_node.get("divCode") or root_node.get("key") or "root",
            biz_obj_code=data.get("bizObjCode") or root_node.get("bizObjCode"),
            app_code=data.get("appCode") or root_node.get("appCode") or page_json.get("appCode"),
            domain_key=data.get("domainKey") or root_node.get("domainKey") or page_json.get("domainKey"),
        )
    )
    _walk_json_tree(root_node, None, manifest, [])

    action_el = data.get("actionEL")
    if action_el:
        manifest.actions = _deduplicate(manifest.actions + _extract_actions_from_action_el(action_el))

    for region in manifest.regions:
        region.scan_priority = PRIORITY_MAP.get(region.region_type, 999)
    return manifest


def _walk_json_tree(
    node: dict[str, Any],
    parent_region: Region | None,
    manifest: PageManifest,
    column_groups: list[str],
    parent_node: dict[str, Any] | None = None,
) -> None:
    region = _maybe_build_region(node, parent_region)
    current_region = region if region else parent_region
    if region is not None:
        manifest.regions.append(region)

    template_node = TemplateNode(
        key=node.get("key") or node.get("divCode") or "",
        fieldid=node.get("divCode") or node.get("key") or "",
        label=node.get("label") or node.get("title") or "",
        node_type=node.get("nodeType") or "",
        component_name=node.get("name") or "",
        data_field=node.get("dataField") or node.get("fieldname"),
        actions=_extract_action_keys(node),
        raw=node,
    )
    manifest.template_nodes.append(template_node)

    tab_child_candidate = _maybe_build_tab_candidate_from_child_card(node, parent_region)
    if tab_child_candidate is not None:
        manifest.tabs.append(tab_child_candidate)

    candidate = _maybe_build_candidate(node, current_region, column_groups, parent_node)
    if candidate is not None:
        _append_candidate(manifest, node, candidate, current_region)

    next_column_groups = column_groups
    if node.get("nodeType") == "column" and node.get("children"):
        label = str(node.get("label") or node.get("title") or "").strip()
        if label:
            next_column_groups = [*column_groups, label]
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _walk_json_tree(child, current_region, manifest, next_column_groups, node)


def _maybe_build_region(node: dict[str, Any], parent_region: Region | None) -> Region | None:
    region_type = _classify_region(node)
    if region_type is None:
        return None
    fieldid = _source_direct_fieldid(node) or region_type
    return Region(
        key=node.get("key") or node.get("divCode") or region_type,
        fieldid=fieldid,
        label=node.get("label") or node.get("title") or node.get("name") or "",
        region_type=region_type,
        node_type=node.get("nodeType") or "",
        component_name=node.get("name") or "",
        parent_region_key=parent_region.key if parent_region else None,
        visible_by_config=node.get("hide") != 1,
        scan_priority=999,
        entity_uri=_extract_entity_uri(node) or (parent_region.entity_uri if parent_region else None),
        runtime_fieldids=_region_runtime_fieldids(node, region_type, str(fieldid)),
    )


def _classify_region(node: dict[str, Any]) -> str | None:
    return RENDER_ADAPTERS.classify_region(node)


def _maybe_build_candidate(
    node: dict[str, Any],
    current_region: Region | None,
    column_groups: list[str] | None = None,
    parent_node: dict[str, Any] | None = None,
) -> ElementCandidate | None:
    if current_region is None:
        return None
    if node.get("nodeType") not in {"leafItem", "formItem", "column", "tabPane"}:
        return None
    data_field = node.get("dataField") or node.get("fieldname")
    entity_uri = current_region.entity_uri if current_region else None
    label, title, resolved_column_groups = _resolve_column_label_and_groups(node, current_region, column_groups or [])
    return ElementCandidate(
        key=node.get("key") or node.get("divCode") or "",
        fieldid=_source_direct_fieldid(node, parent_node) or str(node.get("key") or "").strip(),
        label=label,
        title=title,
        region_key=current_region.key if current_region else None,
        region_fieldid=current_region.fieldid if current_region else None,
        element_type=node.get("nodeType") or "",
        component_name=node.get("name") or "",
        data_field=data_field,
        entity_uri=entity_uri,
        property_uri=_extract_property_uri(node, entity_uri, data_field),
        rightflag=node.get("rightflag"),
        visible_by_config=node.get("hide") != 1,
        action_keys=_extract_action_keys(node),
        runtime_fieldids=_candidate_runtime_fieldids(node, current_region, parent_node),
        verified_runtime_fieldids=_verified_candidate_runtime_fieldids(node, current_region, parent_node),
        column_groups=resolved_column_groups,
        raw=node,
    )


def _resolve_column_label_and_groups(
    node: dict[str, Any],
    current_region: Region | None,
    column_groups: list[str],
) -> tuple[str, str, list[str]]:
    label = str(node.get("label") or "")
    title = str(node.get("title") or "")
    is_table_column = node.get("nodeType") == "column" or getattr(current_region, "region_type", None) == "main_table"
    if not is_table_column or column_groups:
        return label, title, list(column_groups)

    display_name = str(node.get("displayName") or node.get("displayname") or "").strip()
    path = [part.strip() for part in re.split(r"[.．]", display_name) if part.strip()]
    if len(path) < 2:
        return label, title, []

    groups = [_strip_column_group_unit(part) for part in path[:-1]]
    leaf = path[-1]
    return leaf, leaf if not title else leaf, groups


def _strip_column_group_unit(value: str) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s*[（(][^（）()]*[）)]\s*$", "", text).strip() or text


def _maybe_build_tab_candidate_from_child_card(
    node: dict[str, Any],
    parent_region: Region | None,
) -> ElementCandidate | None:
    if parent_region is None or parent_region.region_type != "tab_bar":
        return None
    if node.get("nodeType") != "card":
        return None
    label = node.get("label") or node.get("title") or ""
    if not label:
        return None
    div_code = node.get("divCode") or node.get("key") or ""
    fieldid = f"{div_code}_tab" if div_code and not str(div_code).endswith("_tab") else str(div_code)
    return ElementCandidate(
        key=node.get("key") or div_code,
        fieldid=fieldid,
        label=label,
        title=node.get("title") or "",
        region_key=parent_region.key,
        region_fieldid=parent_region.fieldid,
        element_type="tab",
        component_name=node.get("name") or "",
        entity_uri=parent_region.entity_uri,
        runtime_fieldids=[fieldid] if fieldid else [],
        raw=node,
    )


def _append_candidate(
    manifest: PageManifest,
    node: dict[str, Any],
    candidate: ElementCandidate,
    current_region: Region | None,
) -> None:
    region_type = current_region.region_type if current_region else None
    node_type = node.get("nodeType")
    if region_type == "query_box":
        manifest.query_fields.append(candidate)
        return
    if region_type == "tab_bar" and node_type == "leafItem":
        manifest.tabs.append(candidate)
        return
    if region_type == "tab_bar" and _looks_like_form_tab_item(node):
        manifest.tabs.append(candidate)
        return
    if node_type == "column" or (region_type == "main_table" and node_type == "formItem"):
        manifest.table_columns.append(candidate)
        return
    if node_type == "leafItem" and region_type == "tree":
        manifest.trees.append(candidate)
        return
    if region_type == "dialog_page":
        manifest.dialogs.append(candidate)
        return
    if node_type == "leafItem" and region_type in {"top_action_bar", "table_action_bar"}:
        manifest.actions.append(candidate)
        return
    manifest.fields.append(candidate)


def _extract_actions_from_action_el(action_el: Any) -> list[ElementCandidate]:
    actions: list[ElementCandidate] = []
    if isinstance(action_el, dict):
        items = action_el.items()
    elif isinstance(action_el, list):
        items = enumerate(action_el)
    else:
        return actions
    for action_name, node in items:
        if not isinstance(node, dict):
            continue
        actions.append(
            ElementCandidate(
                key=node.get("key") or str(action_name),
                fieldid=node.get("divCode") or node.get("key") or str(action_name),
                label=node.get("label") or node.get("title") or str(action_name),
                title=node.get("title") or "",
                region_key=((node.get("parentKeys") or [])[-1] if node.get("parentKeys") else None),
                region_fieldid=None,
                element_type=node.get("nodeType") or "",
                component_name=node.get("name") or "",
                data_field=node.get("dataField") or node.get("fieldname"),
                entity_uri=_extract_entity_uri(node),
                property_uri=_extract_property_uri(
                    node,
                    _extract_entity_uri(node),
                    node.get("dataField") or node.get("fieldname"),
                ),
                rightflag=node.get("rightflag"),
                visible_by_config=node.get("hide") != 1,
                action_keys=_extract_action_keys(node),
                runtime_fieldids=_dedupe_strings([node.get("divCode"), node.get("key")]),
                raw=node,
            )
        )
    return actions


def _looks_like_form_tab_item(node: dict[str, Any]) -> bool:
    node_type = str(node.get("nodeType") or "").lower()
    component_name = str(node.get("name") or "").lower()
    return node_type in {"tabpane", "tab", "pane"} or component_name in {"ydftabpane", "tabpane"}


def _extract_action_keys(node: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    actions = node.get("actions")
    if isinstance(actions, dict):
        for name, value in actions.items():
            if isinstance(value, dict):
                _append_action_aliases(keys, value)
            else:
                found = False
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            before = len(keys)
                            _append_action_aliases(keys, item)
                            found = found or len(keys) > before
                if not found:
                    keys.append(str(name))
    elif isinstance(actions, list):
        for value in actions:
            if isinstance(value, dict):
                _append_action_aliases(keys, value)
            elif value:
                keys.append(str(value))
    if node.get("rightflag"):
        keys.append(str(node["rightflag"]))
    return list(dict.fromkeys(keys))


def _append_action_aliases(keys: list[str], action: dict[str, Any]) -> None:
    for field in ("key", "action", "name", "divCode", "label", "title"):
        value = action.get(field)
        if value:
            keys.append(str(value))


def _deduplicate(items: list[ElementCandidate]) -> list[ElementCandidate]:
    seen: set[tuple[str, str]] = set()
    result: list[ElementCandidate] = []
    for item in items:
        key = (item.fieldid, item.label)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _region_runtime_fieldids(node: dict[str, Any], region_type: str, fieldid: str) -> list[str]:
    component_name = str(node.get("name") or "")
    if region_type == "main_table" or component_name == "LCDTable":
        return _dedupe_strings([f"{fieldid}_table"])
    if region_type == "tree" or component_name == "LCDTree":
        return _dedupe_strings(
            [
                fieldid,
                f"{fieldid}_search_input",
                f"{fieldid}_search_suffix",
            ]
        )
    if region_type == "query_box" or component_name == "LCDQueryString":
        return _dedupe_strings(
            [
                f"{fieldid}_query_icon",
                fieldid,
                f"{fieldid}_fuzzy_input",
                f"{fieldid}_fuzzy_btn",
                f"{fieldid}_fuzzy_icon",
                f"{fieldid}_btn",
                f"{fieldid}_plan",
            ]
        )
    return _dedupe_strings([fieldid])


def _candidate_runtime_fieldids(
    node: dict[str, Any], region: Region | None, parent_node: dict[str, Any] | None = None
) -> list[str]:
    div_code = _source_direct_fieldid(node, parent_node)
    data_field = str(node.get("dataField") or node.get("fieldname") or "")
    component_name = str(node.get("name") or "")
    region_fieldid = str(getattr(region, "fieldid", "") or "")
    runtime_region_fieldid = _runtime_region_fieldid(region)
    values: list[str] = []

    if div_code:
        values.append(div_code)
    if component_name == "LCDTable":
        values.append(f"{div_code}_table")
    if region and region.region_type == "main_table" and data_field:
        values.append(f"{region_fieldid}_{data_field}")
        if runtime_region_fieldid and runtime_region_fieldid != region_fieldid:
            values.append(f"{runtime_region_fieldid}_{data_field}")
    if data_field and region_fieldid and region and region.region_type in {"content_card", "query_box", "dialog_page"}:
        for direct_id in _verified_candidate_runtime_fieldids(node, region, parent_node):
            values.append(direct_id)
            if component_name in {"YDFSelect", "YDFTreeSelect"}:
                values.extend(
                    [
                        f"{direct_id}_input",
                        f"{direct_id}_suffix",
                        f"{direct_id}_search_input",
                    ]
                )
            elif component_name == "YDFDatePicker":
                values.extend([f"{direct_id}_input", f"{direct_id}_suffix"])
        base = f"{region_fieldid}_{data_field}"
        values.append(base)
        if _is_modal_reference_component(component_name):
            values.extend(
                [
                    f"{base}_input",
                    f"{base}_btn",
                    f"{base}_table",
                    f"{base}_tree",
                    f"{base}_tree_search",
                    f"{base}_modal_ok",
                    f"{base}_modal_cancel",
                ]
            )
            if component_name == "YDFTreeModalSelect":
                values.append(f"{base}_input_search_input")
        elif component_name in {"YDFTreeSelect", "YDFSelect", "YDFDatePicker", "YDFDateRange"}:
            values.extend([f"{base}_input", f"{base}_suffix"])
            if component_name in {"YDFSelect", "YDFTreeSelect"}:
                values.append(f"{base}_search_input")
        elif component_name in {"YDFCheckboxGroup", "YDFRadio"}:
            values.append(f"{base}_checkbox")
            values.append(f"{base}_radio")
    return _dedupe_strings(values)


def _verified_candidate_runtime_fieldids(
    node: dict[str, Any], region: Region | None, parent_node: dict[str, Any] | None = None
) -> list[str]:
    data_field = str(node.get("dataField") or node.get("fieldname") or "")
    if region and region.region_type == "main_table" and data_field:
        return [f"{region.fieldid}_{data_field}"]
    direct_fieldid = str(node.get("fieldid") or node.get("divCode") or "").strip()
    if node.get("parseChild") == 0:
        direct_fieldid = str(node.get("divCode") or "").strip()
    return [direct_fieldid] if direct_fieldid else []


def _source_direct_fieldid(node: dict[str, Any], parent_node: dict[str, Any] | None = None) -> str:
    """Mirror UIParser and ViewPanel's direct widget identity rules."""
    if not node.get("fieldid") and node.get("dataField") and (parent_node or {}).get("nodeType") == "form":
        parent_fieldid = str((parent_node or {}).get("divCode") or "").strip()
        data_field = str(node.get("dataField") or "").strip()
        if parent_fieldid and data_field:
            return f"{parent_fieldid}_{data_field}"
    if node.get("parseChild") == 0:
        return str(node.get("divCode") or "").strip()
    return str(node.get("fieldid") or node.get("divCode") or "").strip()


def _runtime_region_fieldid(region: Region | None) -> str:
    if region is None:
        return ""
    for value in region.runtime_fieldids:
        if value:
            return value
    return str(region.fieldid or "")


def _is_modal_reference_component(component_name: str) -> bool:
    normalized = component_name.lower().replace("-", "").replace("_", "")
    return normalized in {"ydftablemodalselect", "ydftreemodalselect", "ydfreferselect"}


def _dedupe_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _extract_entity_uri(node: dict[str, Any]) -> str | None:
    info = (node.get("enty") or {}).get("info") if isinstance(node.get("enty"), dict) else None
    if isinstance(info, dict) and info.get("uri"):
        return str(info["uri"])
    if isinstance(node.get("info"), dict) and node["info"].get("uri"):
        return str(node["info"]["uri"])
    raw_uri = node.get("entityUri") or node.get("entityURI")
    return str(raw_uri) if raw_uri else None


def _extract_property_uri(node: dict[str, Any], entity_uri: str | None, data_field: str | None) -> str | None:
    raw_uri = node.get("uri") or node.get("propertyUri") or node.get("propertyURI")
    if raw_uri:
        return str(raw_uri)
    if entity_uri and data_field:
        return f"{entity_uri}.{data_field}"
    return None
