"""单据设计器组件处理器注册表（recorder 的核心资产）。

一张「单据组件 → DSL step」的映射表。每个组件一个 ``ComponentHandler``，封装：

  - ``recognize(event)``：该 DOM 事件是否归属本组件，命中则返回 operation 名；
  - ``build_target(operation, events)``：从事件流构建该组件的 target dict。

主转换循环据此把录制事件归类为 ``(component, operation)``，再构建 target。
**新增一个单据组件 = 新增一个 handler**，主流程不动。

本注册表是 recorder 对 DSL 契约的「知识内化」：组件识别与 target 形状由
recorder 自维护，遵循 ydf-browser 的 ``COMPONENT_TARGET_SCHEMAS`` /
``schemas/dsl.schema.json`` 约定，但**不 import 任何 ydf_browser 代码**。
ydf-browser 新增/变更组件时，在此增改 handler 即可。

handler 列表 ``HANDLERS`` 的顺序即识别优先级，严格对应原 ``classify_event``
的 if 分支顺序，保证迁移后行为不变。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from .models import RecordedEvent

HandlerRecognize = Callable[[RecordedEvent], str | None]
HandlerBuildTarget = Callable[[str, list[RecordedEvent]], dict[str, Any]]


# ── 谓词与常量 ──────────────────────────────────────────────

# 工具栏动作的已知中文标签（label → 规范 label，当前为恒等映射，保留扩展点）。
# 来源：YonDiF 标准单据动作 YBillActionEnum（YAdd/YSave/YDelete/YStop/YUnStop/YExport/YImport...）
# 对应的按钮文案 + 常见工具栏文案。新增标签时保持恒等映射。
_KNOWN_ACTION_LABELS: dict[str, str] = {
    "新增": "新增", "删除": "删除", "保存": "保存", "提交": "提交",
    "编辑": "编辑", "详情": "详情", "导入": "导入", "导出": "导出",
    "打印": "打印", "审核": "审核", "弃审": "弃审",
    "返回": "返回", "查询": "查询",
    # ★ 问题3修复：确定/确认/取消 是弹窗按钮词汇，已从已知动作表移除 ——
    #   YonDiF 自定义弹窗不设 in_dialog 标志，这三个词会把弹窗确认按钮
    #   误判为 toolbar.click。页面工具栏真按钮由 region 路径识别。
    "重置": "重置", "增行": "增行", "删行": "删行", "更多": "更多",
    "暂存": "暂存", "停用": "停用", "启用": "启用", "刷新": "刷新",
    "批量": "批量", "操作": "操作", "处理": "处理", "流程": "流程",
    "批量操作": "批量操作", "批量处理": "批量处理",
}

# 表格行操作按钮的可识别文本。
# 来源：YonDiF 列表页常见行操作文案（含批量操作菜单项）。
_TABLE_ROW_ACTION_TEXTS = (
    "编辑", "详情", "删除", "查看", "修改",
    "送审", "驳回", "审核", "弃审", "启用", "停用",
    "终止", "撤回", "复制", "参照", "签章",
)

# action.click 的已知 fieldid（与 ydf-browser executor._RETURN_ACTION_FIELDIDS 对齐）
_ACTION_CLICK_FIELDIDS = frozenset({"pageHeader_return", "ymbtl_backup"})
# action.click 的已知标签
_ACTION_CLICK_LABELS = frozenset({"返回", "返回列表"})

# 可合并的 (component, operation) 对：连续同类事件合并为单个 step。
_COALESCEABLE_PAIRS = frozenset(
    {("form", "fill"), ("query", "search"), ("table_row_selection", "select"),
     ("editable_table", "fill_row"), ("import", "upload"), ("attachment", "upload"),
     ("dialog", "confirm"), ("dialog", "cancel")}
)


def is_button_click(event: RecordedEvent) -> bool:
    """事件是否是按钮类点击（button/a/span/div 且有文本）。"""
    return (
        event.type == "click"
        and event.target.tag_name in ("button", "a", "span", "div")
        and bool(event.target.text)
    )


def is_form_input(event: RecordedEvent) -> bool:
    """事件是否是表单输入（input/textarea/select 的 input/change）。

    ★ P1-6：富文本（contenteditable）的 input 事件也算表单输入 —
    inject.js 的 detectWidgetType 将其标为 widget_type='richtext'，
    回放端 form.fill 的填值脚本已支持 [contenteditable="true"]。
    """
    if event.type not in ("input", "change"):
        return False
    if event.target.tag_name in ("input", "textarea", "select"):
        return True
    return event.type == "input" and event.target.widget_type == "richtext"


def is_switch_toggle(event: RecordedEvent) -> bool:
    """事件是否是 Switch 开关组件的切换操作。

    YonDiF YDFSwitch 渲染为 ``<button class="wui-switch is-checked">``，
    由 inject.js 的 ``isSwitchControl`` 检测并设置 ``is_switch=True``。
    不在表格内时（弹窗/表单中的开关），归入 form.fill。
    """
    if not event.target.is_switch:
        return False
    # 表格内的 switch 由 table_row_selection 处理
    if event.target.in_table:
        return False
    return True


def normalize_field_label(event: RecordedEvent) -> str:
    """从事件提取规范化的字段标签（label_text → 短 text → placeholder → fieldid/name）。"""
    label = event.target.label_text
    if label:
        return label
    text = (event.target.text or "").strip()
    if text and len(text) < 50:
        return text
    placeholder = event.target.placeholder
    if placeholder:
        return placeholder
    return event.target.fieldid or event.target.name or "unknown"


# ── target 构建器（按 component 索引）────────────────────────

def _build_form(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    """构建 form.fill target。

    对于下拉选择字段，优先使用 display_text（如 '2 阶段性'），
    因为 ydf-browser 的 form.fill 期望用户看到的显示值。
    对于 Switch 开关组件，值用 true/false 表示开/关状态。
    对于参照选择字段（问题5），优先使用结构化值（如 {"row_number": 2}），
    回放端按行号点选，避免动态内容匹配失败。
    """
    fields: dict[str, Any] = {}
    for e in events:
        label = normalize_field_label(e)
        # ★ Switch 开关：优先使用 JS 端捕获的状态值（readSwitchState，
        #   问题4），无状态值时默认 "true"（用户主动切换通常是为了打开）
        if is_switch_toggle(e):
            state = (e.target.value or "").strip().lower()
            fields[label] = state if state in ("true", "false") else "true"
            continue
        # ★ 参照选择（问题5）：结构化行号值优先，回放按行号点选
        if e.target.structured_value:
            fields[label] = e.target.structured_value
            continue
        # 下拉选择：优先 display_text（含值+名称），其次 value
        val = e.target.display_text or e.target.value or ""
        fields[label] = val
    return {"fields": fields}


# 工具栏已知动作词，用于拆分拼接的 label（如 "新增提交删除" → "新增"）
_TOOLBAR_ACTION_WORDS = [
    "增值税发票", "弃审", "审核", "导入", "导出", "新增", "提交",
    "删除", "保存", "打印", "更多", "关闭", "取消", "刷新", "查询",
]


def _split_concatenated_label(label: str) -> str:
    """如果 label 是多个已知工具栏动作词的拼接，返回第一个。"""
    if not label or len(label) <= 4:
        return label
    for action in _TOOLBAR_ACTION_WORDS:
        if label.startswith(action):
            remaining = label[len(action):]
            if not remaining:
                return label
            for action2 in _TOOLBAR_ACTION_WORDS:
                if remaining.startswith(action2):
                    return action
            return label
    return label


def _build_toolbar(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    label = (events[0].target.text or "").strip()
    # ★ 安全兜底：拆分拼接的 label（"新增提交删除" → "新增"）
    label = _split_concatenated_label(label)
    if label in _KNOWN_ACTION_LABELS:
        label = _KNOWN_ACTION_LABELS[label]
    result: dict[str, Any] = {"label": label}
    # If this event was synthesized from hover→click, display_text carries sub_label
    sub_label = (events[0].target.display_text or "").strip()
    if sub_label and sub_label != label:
        result["sub_label"] = sub_label
    return result


def _build_tab(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    return {"label": (events[0].target.text or "").strip()}


def _build_tree(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    event = events[0]
    label = (event.target.text or "").strip()
    result: dict[str, Any] = {"label": label}
    # 树节点的 aria-label 通常比 text 更干净
    if event.target.label_text:
        result["label"] = event.target.label_text
    return result


def _build_query(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    conditions: list[dict[str, str]] = []
    for e in events:
        if is_form_input(e):
            label = normalize_field_label(e)
            value = e.target.value or ""
            if label and value:
                conditions.append({"field": label, "equals": value})
    return {"conditions": conditions} if conditions else {}


def _pick_best_match_column(row_data: list[dict[str, str]]) -> dict[str, str] | None:
    """从行数据中选取最适合作为唯一标识的列。

    优先级：
    1. 列名含 "编码"/"代码"/"编号"/"单号"/"ID" 等强标识词
    2. 列名含 "名称" 的列（次优，可能有重名）
    3. 第一个可用列
    """
    if not row_data:
        return None
    # 强标识关键词
    strong_patterns = re.compile(r"编码|代码|编号|单号|ID|标识|流水号|序列号", re.IGNORECASE)
    # 次优关键词
    weak_patterns = re.compile(r"名称|标题|主题", re.IGNORECASE)
    # 排除词（状态/日期/金额等易重复值）
    exclude_patterns = re.compile(r"状态|日期|金额|数量|比例|百分比|序号|操作|选择", re.IGNORECASE)

    strong_match = None
    weak_match = None
    first_match = None
    for item in row_data:
        col = item.get("column", "")
        val = item.get("value", "")
        if not col or not val:
            continue
        if first_match is None:
            first_match = item
        if exclude_patterns.search(col):
            continue
        if strong_patterns.search(col):
            return item  # 强匹配直接返回
        if weak_match is None and weak_patterns.search(col):
            weak_match = item
    return weak_match or first_match


def _build_table_row_selection(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    """构建 table_row_selection target。

    ★ 问题5：优先用 ``row_number`` 行号定位 —— 申请单号等业务单据号每次
    运行动态生成，内容匹配在全新环境回放必然失败；行号在同等数据准备下
    稳定。无行号信息时才回退到 ``match:{column, equals}`` 内容匹配。

    ★ 优先级：
    1. ``editable_row_number``（JS 端提取的行号，最可靠）
    2. 从 ``row_data`` 中选取唯一标识列构建 ``match``
    3. 从 ``cell_text`` / ``column_header`` 构建 ``match``
    4. 回退到 ``row_number: 1``（checkbox/switch change 场景）
    5. 回退到 ``select_all:true``
    """
    # 优先级 1：行号定位
    for e in events:
        row_num = e.target.editable_row_number
        if row_num and row_num > 0:
            return {"row_number": row_num}
    # 优先级 2：从 row_data 中选取唯一标识列
    for e in events:
        if e.target.row_data:
            best = _pick_best_match_column(e.target.row_data)
            if best:
                return {"match": {"column": best["column"], "equals": best["value"]}}
    # 优先级 3：cell_text + column_header（原有逻辑）
    for e in events:
        col = e.target.column_header
        val = e.target.cell_text or e.target.row_text
        if col and val:
            return {"match": {"column": col, "equals": val}}
    # 回退 1：有 value 说明是 checkbox/switch change，默认选第一行
    for e in events:
        if e.target.value:
            return {"row_number": 1}
    return {"select_all": True}


def _build_table_row_action(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    """构建 table_row_action target。

    优先用 ``match:{column, equals}`` 精确匹配行（与 ydf-browser 示例对齐）。
    """
    event = events[0]
    result: dict[str, Any] = {"action": (event.target.text or "").strip()}
    # 优先从 row_data 选取唯一标识列
    if event.target.row_data:
        best = _pick_best_match_column(event.target.row_data)
        if best:
            result["match"] = {"column": best["column"], "equals": best["value"]}
            return result
    col = event.target.column_header
    val = event.target.cell_text or event.target.row_text
    if col and val:
        result["match"] = {"column": col, "equals": val}
    elif event.target.value:
        result["row_number"] = 1
    return result


def _build_dialog(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    label = (events[0].target.text or "").strip()
    result: dict[str, Any] = {"label": label} if label else {}
    fid = (events[0].target.fieldid or "").strip()
    if fid.endswith(("_modal_ok", "_modal")):
        # ★ 参照选择器自身的确认按钮：form.fill 的参照流程可能已自动确认并
        #   关闭选择器。回放时按 fieldid 定位该按钮：找不到（已被 fill 确认）
        #   则跳过，避免误点外层弹窗的同名确定按钮
        result["optional"] = True
        if fid:
            result["fieldid"] = fid
    return result


# ── 新增组件构建器 ─────────────────────────────────────────

def _build_action(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    """构建 action.click target。"""
    event = events[0]
    result: dict[str, Any] = {}
    fid = (event.target.fieldid or "").strip()
    label = (event.target.text or "").strip()
    if fid:
        result["fieldid"] = fid
    if label:
        result["label"] = label
    return result


def _build_attachment_upload(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    """构建 attachment.upload target。

    浏览器安全模型拿不到完整文件路径，只能通过后续 file change 事件拿到
    文件名（converter._backfill_upload_filenames 回填），生成带文件名的
    占位符供用户手动补全路径。
    """
    event = events[0]
    label = (event.target.text or "上传附件").strip()
    fname = next(
        (e.target.uploaded_file_name for e in events if e.target.uploaded_file_name),
        None,
    )
    file_placeholder = f"<请填写文件路径: {fname}>" if fname else "<请填写文件路径>"
    return {
        "label": label,
        "attachments": [{"type": "<请填写附件类型>", "file": file_placeholder}],
    }


def _build_import_upload(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    """构建 import.upload target。

    浏览器安全模型拿不到完整文件路径，只能通过后续 file change 事件拿到
    文件名（converter._backfill_upload_filenames 回填），生成带文件名的
    占位符供用户手动补全路径。
    """
    event = events[0]
    label = (event.target.text or "导入").strip()
    fname = next(
        (e.target.uploaded_file_name for e in events if e.target.uploaded_file_name),
        None,
    )
    return {
        "label": label,
        "file": f"<请填写文件路径: {fname}>" if fname else "<请填写文件路径>",
    }


def _build_import_download_template(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    """构建 import.download_template target。"""
    event = events[0]
    label = (event.target.text or "导入").strip()
    # 尝试从按钮上下文提取模版名称
    template = event.target.aria_label or event.target.title_attr or None
    result: dict[str, Any] = {"label": label}
    if template and template != label:
        result["template"] = template
    return result


def _build_amount_unit(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    """构建 amount_unit.set target。"""
    event = events[0]
    # 优先使用显示文本（如 "万元"），其次使用 value
    value = event.target.display_text or event.target.value or ""
    if not value:
        value = "<请填写金额单位>"
    return {"value": str(value).strip()}


def _build_transfer_dialog(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    """构建 transfer_dialog.select target。

    从事件流中提取穿梭框标题和选中的项。
    """
    result: dict[str, Any] = {}
    items: list[str] = []
    # 尝试从事件中提取弹窗标题
    for e in events:
        if e.target.popup_title and "title" not in result:
            result["title"] = e.target.popup_title
    # 提取被点击的项文本（排除按钮类元素）
    for e in events:
        text = (e.target.text or "").strip()
        if text and not is_button_click(e) and text not in ("确定", "确认", "取消", "关闭"):
            if text not in items:
                items.append(text)
    if items:
        result["items"] = items
    result["move"] = "to_right"
    result["confirm"] = True
    return result


def _build_notification(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    """构建 notification.close / notification.assert target。"""
    event = events[0]
    label = (event.target.text or "").strip()
    message = (event.target.notification_text or "").strip()
    result: dict[str, Any] = {}
    if operation == "assert":
        # 优先用通知正文；关闭按钮自身文本（常为 ×）无意义
        if message:
            result["contains"] = message
        elif label:
            result["contains"] = label
        return result
    if label:
        result["label"] = label
    if message:
        # close target 允许 contains：回放端用于匹配要关闭的通知，避免误关
        result["contains"] = message
    return result


def _build_form_assert(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    """构建 form.assert_values target：{fields: {字段名: 期望值}}。"""
    event = events[0]
    t = event.target
    name = (t.label_text or t.aria_label or t.placeholder or t.fieldid or "").strip()
    value = (t.value if t.value not in (None, "") else t.display_text) or ""
    result: dict[str, Any] = {}
    if name:
        result["fields"] = {name: str(value)}
    elif t.fieldid:
        result["fieldid"] = t.fieldid
        result["equals"] = str(value)
    return result


def _pick_unique_match_column(row_data: list[dict[str, str]]) -> tuple[str, str] | None:
    """从行数据中选唯一标识列（优先编码/名称/ID 类列）。"""
    priority = ("编码", "代码", "名称", "id", "ID", "号")
    fallback: tuple[str, str] | None = None
    for item in row_data:
        col = (item.get("column") or "").strip()
        val = (item.get("value") or "").strip()
        if not col or not val:
            continue
        if fallback is None:
            fallback = (col, val)
        for kw in priority:
            if kw in col:
                return (col, val)
    return fallback


def _build_table_assert(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    """构建 table.assert_row_values target：{match, fields}（schema 必需两项）。"""
    event = events[0]
    t = event.target
    row_data = t.row_data or []
    result: dict[str, Any] = {}
    match = _pick_unique_match_column(row_data)
    if match:
        result["match"] = {"column": match[0], "equals": match[1]}
    fields = {
        (item.get("column") or "").strip(): (item.get("value") or "").strip()
        for item in row_data
        if (item.get("column") or "").strip() and (item.get("value") or "").strip()
    }
    if fields:
        result["fields"] = fields
    if "match" not in result and t.cell_text and t.column_header:
        result["match"] = {"column": t.column_header, "equals": t.cell_text}
        result.setdefault("fields", {t.column_header: t.cell_text})
    if not t.in_table:
        # 非 table 检查点不应走到这里（classify 已分流），防御性返回空
        return {}
    return result


def _build_popup_reference(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    target = events[0].target
    result: dict[str, Any] = {}
    if target.popup_title:
        result["title"] = target.popup_title
    # 优先「列 + 值」精确匹配；否则回退整行 value
    if target.column_header and target.cell_text:
        result["match"] = {"column": target.column_header, "equals": target.cell_text}
    elif target.cell_text:
        result["value"] = target.cell_text
    elif target.row_text:
        result["value"] = target.row_text
    return result


def _parse_editable_fieldid(fid: str | None) -> tuple[str, str, int] | None:
    """从 fieldid 解析可编辑单元格的 ``(table, column, row_number)``。

    遵循 ydf 规则 ``<tableFieldid>_<dataField>_<rowIndex>``（rowIndex 0-based）。
    比 DOM 遍历可靠（真实页面的行 class 常不匹配通用选择器）。
    支持带 ``_btn_i`` / ``_btn`` 后缀的参照触发器 fieldid。
    """
    if not fid:
        return None
    # 剥离参照触发器后缀
    cleaned = re.sub(r"_(?:btn(?:_i|_icon)?)$", "", fid)
    match = re.match(r"^(.+)_(.+?)_(\d+)$", cleaned)
    if not match:
        return None
    return (match.group(1), match.group(2), int(match.group(3)) + 1)


def _build_editable_table(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    """构建 editable_table target。

    字段名优先使用中文标签（label_text / column_header），
    仅在标签不可用时回退到 fieldid 解析结果——与 ydf-browser 示例对齐。
    同列多次输入时，后值覆盖前值（如 price: '1' → price: '1,000'）。

    对于参照字段（structured_value 已设置），输出结构化值：
    ``{filter: "搜索文本", match: {column: "列名", equals: "值"}}``

    ★ JS 注入的 editable_column / editable_table_name 经常误提取表格第一列
    "序号" 作为表名。此函数优先用 fieldid 解析，仅在 JS 值不可疑时才采用。
    """
    first = events[0].target
    # ★ 收集字段条目：(col, column_group, val) 三元组列表
    # 用列表而非 dict，以支持同名叶子列在不同 column_group 下的场景
    field_entries: list[tuple[str, Any, Any]] = []
    row_number = first.editable_row_number
    # ★ 不信任 JS 注入的 editable_table_name 当它是 "序号" 等常见误提取值
    # ★ 如果 fieldid 解析出了表名，优先使用 fieldid 结果
    first_parsed = _parse_editable_fieldid(first.fieldid)
    table_name = first.editable_table_name
    if table_name and (_is_suspicious_js_metadata(table_name) or first_parsed):
        table_name = None
    if first_parsed and not first_parsed[0].isdigit():
        table_name = first_parsed[0]
        if row_number is None:
            row_number = first_parsed[2]

    for e in events:
        parsed = _parse_editable_fieldid(e.target.fieldid)
        # ★ 不信任 JS 注入的 editable_column 当它可疑（如 "序号"、纯数字）
        # ★ 如果 fieldid 解析出了列名，也不信任 JS 注入
        js_col = e.target.editable_column
        if js_col and (_is_suspicious_js_metadata(js_col) or parsed):
            js_col = None
        # ★ 不使用 label_text 当它看起来是输入值（如 "100"）而非列名
        label = e.target.label_text
        label_is_value = False
        if label and _looks_like_input_value(label, e.target.value):
            label = None
            label_is_value = True
        # ★ 当 label 被过滤为输入值时，不使用 normalize_field_label（它会读同一个 label_text）
        # 优先用 fieldid 解析的列名，其次可信的中文标签
        if label_is_value and parsed:
            col = parsed[1]
        else:
            col = (
                js_col
                or e.target.column_header
                or label
                or normalize_field_label(e)
                or (parsed[1] if parsed else None)
            )
        # normalize_field_label 可能返回 "unknown"，不理想，用 fieldid 兜底
        if (not col or col == "unknown") and parsed:
            col = parsed[1]
        # ★ 拒绝纯数字列名（如 '10'），说明 fieldid 解析出了 data-field ID
        # 而非中文表头。尝试用 fieldid 解析结果优先，然后 column_header 等
        if col and col.isdigit():
            col = (
                (parsed[1] if parsed else None)  # ★ fieldid 解析结果优先
                or e.target.column_header
                or e.target.placeholder
                or e.target.aria_label
                or None
            )
            # ★ 如果上述都不行，检查 title_attr 但排除等于 value 的情况
            if not col:
                title = e.target.title_attr
                if title and not _looks_like_input_value(title, e.target.value):
                    col = title
        if col:
            # ★ 参照字段：使用 structured_value（{filter, match}）而非标量值
            if e.target.structured_value:
                val = e.target.structured_value
            else:
                val = e.target.value or ""
            # ★ 多级列头：归一化 column_group（单级→字符串，多级→列表）
            cg = (
                _normalize_column_group(e.target.editable_column_group)
                if e.target.editable_column_group else None
            )
            field_entries.append((col, cg, val))
        if parsed:
            if row_number is None:
                row_number = parsed[2]
            # ★ 拒绝纯数字表名（如 '10'）
            parsed_table = parsed[0]
            if table_name is None and not parsed_table.isdigit():
                table_name = parsed_table

    # ★ 表名优先用中文标题：如果 table_name 看起来像 fieldid 或纯数字，
    # 尝试从所有事件的 label_text / text / popup_title 中找更好的中文名称
    if table_name and (_looks_like_fieldid(table_name) or table_name.isdigit()):
        for e in events:
            for candidate in (e.target.label_text, e.target.text, e.target.popup_title):
                if (
                    candidate
                    and not _looks_like_fieldid(candidate)
                    and not candidate.isdigit()
                    and not _is_suspicious_js_metadata(candidate)
                    and len(candidate) <= 20
                ):
                    table_name = candidate
                    break
            if table_name and not _looks_like_fieldid(table_name) and not table_name.isdigit():
                break

    # ★ 构建 fields 输出：
    # - 有 column_group 或同名列 → 数组形式 [{field, column_group?, value}, ...]
    # - 否则 → 对象形式 {col: value, ...}（更简洁，向后兼容）
    # ★ 先按 (field, column_group) 去重，避免 input+change 重复事件
    #   导致 has_dup 误判，强制使用数组形式
    deduped: dict[tuple[str, str | None], tuple[str, Any, Any]] = {}
    for col, cg, val in field_entries:
        key = (col, _cg_key(cg))
        deduped[key] = (col, cg, val)
    unique_entries = list(deduped.values())

    has_group = any(cg is not None for _, cg, _ in unique_entries)
    col_names = [c for c, _, _ in unique_entries]
    has_dup = len(col_names) != len(set(col_names))

    fields: Any = None
    if has_group or has_dup:
        # 数组形式
        fields = []
        for col, cg, val in unique_entries:
            item: dict[str, Any] = {"field": col}
            if cg:
                item["column_group"] = cg
            item["value"] = val
            fields.append(item)
    else:
        # 对象形式：按列名去重，后值覆盖前值
        fields = {}
        for col, _, val in unique_entries:
            fields[col] = val

    result: dict[str, Any] = {}
    if table_name:
        result["table"] = table_name
    if row_number is not None:
        result["row_number"] = row_number
    if fields:
        result["fields"] = fields
    return result


def _is_suspicious_js_metadata(value: str | None) -> bool:
    """判断 JS 注入的 editable_column / editable_table_name 是否明显可疑。

    YonDiF 的 JS 注入经常把表格的第一列表头（如 "序号"）误提取为表名或列名。
    """
    if not value:
        return False
    if value == "序号":
        return True
    if value.isdigit():
        return True
    return False


def _looks_like_input_value(label: str | None, value: str | None) -> bool:
    """判断 label_text 是否实际上是输入值而非列名。

    例如：用户在金额列输入 "100"，JS 可能把 "100" 当作 label_text。
    如果 label 等于 value，或者 label 是纯数字/短文本，它很可能是值而非列名。
    """
    if not label:
        return False
    # label 和 value 相同 → 几乎肯定是值被误当作 label
    if value and label.strip() == value.strip():
        return True
    # 纯数字的 label → 很可能是值（列名几乎不会是纯数字）
    if label.strip().isdigit():
        return True
    return False


def _looks_like_fieldid(value: str) -> bool:
    """判断值是否像 fieldid（如 plzf_skrxx_table）而非中文标题（如 发票内容明细）。"""
    if not value:
        return False
    # 全 ASCII + 下划线 + 数字 → 像 fieldid
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", value))


def _normalize_column_group(group: list[str] | None) -> str | list[str]:
    """归一化 column_group：单级返回字符串（更简洁的 YAML），多级返回列表。"""
    if not group:
        return ""
    if len(group) == 1:
        return group[0]
    return group


def _cg_key(cg: str | list[str] | None) -> str | None:
    """将 column_group 值转为可哈希的 key，用于数组形式去重。"""
    if cg is None:
        return None
    if isinstance(cg, str):
        return cg
    return tuple(cg)


def _build_editable_table_add_row(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    """构建 editable_table.add_row target。"""
    event = events[0]
    result: dict[str, Any] = {"label": (event.target.text or "新增").strip()}
    # 尝试从可编辑表格信息中提取表名
    table_name = event.target.editable_table_name
    if table_name:
        result["table"] = table_name
    return result


def _build_table(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    """构建 table target（click_cell_link 等）。"""
    event = events[0]
    result: dict[str, Any] = {}
    col = event.target.column_header
    val = event.target.cell_text or event.target.row_text
    if col and val:
        result["column"] = col
        result["equals"] = val
    if event.target.text:
        result["label"] = event.target.text.strip()
    return result


# ★ P1-7：工作流批量结果层统计字段解析（与回放端 _WORKFLOW_RESULT_SCAN_SCRIPT 对齐）
_WORKFLOW_RESULT_COUNT_PATTERNS = {
    "total": re.compile(r"(?:总数|总计|总条数|合计|共计|共)\s*[:：]?\s*(\d+)"),
    "succeeded": re.compile(r"(?:成功数|成功条数|成功)\s*[:：]?\s*(\d+)"),
    "failed": re.compile(r"(?:失败数|失败条数|失败)\s*[:：]?\s*(\d+)"),
}


def _parse_workflow_counts(text: str) -> dict[str, int]:
    """从结果层文本解析 total/succeeded/failed 统计。"""
    if not text:
        return {}
    counts: dict[str, int] = {}
    for key, pattern in _WORKFLOW_RESULT_COUNT_PATTERNS.items():
        m = pattern.search(text)
        if m:
            counts[key] = int(m.group(1))
    return counts


def _build_workflow_result(operation: str, events: list[RecordedEvent]) -> dict[str, Any]:
    """构建 workflow_result target（P1-7）。

    assert → 从结果层文本解析 total/succeeded/failed（回放端要求至少一个统计字段）；
    confirm/details → {label: 按钮文本}（label 可省略）。
    """
    event = events[0]
    if operation == "assert":
        text = event.target.workflow_result_text or event.target.text or ""
        return _parse_workflow_counts(text)
    label = (event.target.text or "").strip()
    return {"label": label} if label else {}


_BUILDERS: dict[str, HandlerBuildTarget] = {
    "popup_reference": _build_popup_reference,
    "editable_table": _build_editable_table,
    "editable_table_add": _build_editable_table_add_row,
    "form": _build_form,
    "toolbar": _build_toolbar,
    "tab": _build_tab,
    "tree": _build_tree,
    "query": _build_query,
    "table_row_selection": _build_table_row_selection,
    "table_row_action": _build_table_row_action,
    "table": _build_table,
    "dialog": _build_dialog,
    "action": _build_action,
    "attachment": _build_attachment_upload,
    "import": _build_import_upload,
    "amount_unit": _build_amount_unit,
    "transfer_dialog": _build_transfer_dialog,
    "notification": _build_notification,
    "workflow_result": _build_workflow_result,
}


# ── 识别器（每个返回 operation 名或 None）────────────────────

def _recognize_popup_reference(event: RecordedEvent) -> str | None:
    # 合成事件（由 converter.extract_popup_reference 聚合产生）
    if event.type == "popup_reference_select":
        return "select"
    return None


def _recognize_notification_close(event: RecordedEvent) -> str | None:
    """识别通知提示关闭按钮。"""
    if event.type == "click" and event.target.is_notification_close:
        return "close"
    return None


def _recognize_transfer_dialog(event: RecordedEvent) -> str | None:
    """识别穿梭框选择操作。

    穿梭框内的点击（选中项、移动按钮、确认按钮）都归入 transfer_dialog.select。
    """
    if event.target.is_transfer_item and event.type == "click":
        return "select"
    return None


def _recognize_action(event: RecordedEvent) -> str | None:
    """识别页面动作按钮（如返回按钮）。

    与 ydf-browser executor._RETURN_ACTION_FIELDIDS / _RETURN_ACTION_LABELS 对齐。
    在 toolbar known labels 之前拦截，避免“返回”被误归为 toolbar.click。
    """
    if not is_button_click(event):
        return None
    fid = (event.target.fieldid or "").strip()
    label = (event.target.text or "").strip()
    if fid in _ACTION_CLICK_FIELDIDS:
        return "click"
    if label in _ACTION_CLICK_LABELS:
        # 排除工具栏区域的返回按钮（那些归 toolbar）
        if event.target.region_type not in ("top_action_bar", "table_action_bar"):
            return "click"
    return None


def _recognize_amount_unit(event: RecordedEvent) -> str | None:
    """识别金额单位选择器的变更。"""
    if event.target.is_amount_unit and is_form_input(event):
        return "set"
    return None


def _recognize_attachment_upload(event: RecordedEvent) -> str | None:
    """识别附件上传按钮点击。"""
    if event.type != "click":
        return None
    if not event.target.is_upload_trigger:
        return None
    label = (event.target.text or "").strip()
    # “导入”按钮归 import.upload，不归 attachment
    if "导入" in label:
        return None
    return "upload"


def _recognize_import_upload(event: RecordedEvent) -> str | None:
    """识别导入上传按钮点击。"""
    if event.type != "click":
        return None
    label = (event.target.text or "").strip()
    if "导入" not in label:
        return None
    if event.target.is_upload_trigger:
        return "upload"
    return None


def _recognize_import_download_template(event: RecordedEvent) -> str | None:
    """识别下载模版按钮点击。"""
    if not is_button_click(event):
        return None
    label = (event.target.text or "").strip()
    if "下载模版" in label or "下载模板" in label:
        return "download_template"
    return None


def _recognize_workflow_result(event: RecordedEvent) -> str | None:
    """P1-7：识别工作流批量结果层的确认/查看详情点击。"""
    if event.type != "click" or not event.target.is_workflow_result:
        return None
    label = (event.target.text or "").strip()
    if label in ("确认", "确定"):
        return "confirm"
    if label in ("查看详情", "详情"):
        return "details"
    return None


def _recognize_dialog(event: RecordedEvent) -> str | None:
    if not (event.target.in_dialog and is_button_click(event)):
        return None
    fid = (event.target.fieldid or "").strip()
    # 弹窗内表格的点击是选行/编辑，不是 dialog 按钮
    # ★ 例外：参照选择器自身的确定/取消（fid 以 _modal_ok/_modal 结尾）
    #   DOM 落在选择器表格区域内（in_table=True），需保留为 dialog.confirm
    if event.target.in_table and not fid.endswith(("_modal_ok", "_modal")):
        return None
    # ★ 树选择器内的点击是选节点，不是 dialog 按钮
    # （由 _preprocess_form_interactions 模式 1/5 处理，未捕获则丢弃）
    if event.target.region_type == "tree":
        return None
    # ★ 参照弹窗/穿梭框内的点击是选项，不是 dialog 按钮
    if event.target.is_popup_reference or event.target.is_transfer_item:
        return None
    label = (event.target.text or "").strip()
    # 工具栏动作标签（保存/提交/新增/删除等）即使在弹窗内也归 toolbar，
    # 不归 dialog（与 ydf-browser 示例对齐：保存=toolbar.click 而非 dialog.confirm）
    if label in _KNOWN_ACTION_LABELS:
        return None
    if label in ("确定", "确认", "OK", "Yes", "是"):
        return "confirm"
    if label in ("取消", "关闭", "Cancel", "No", "否"):
        return "cancel"
    return "click"


def _recognize_tab(event: RecordedEvent) -> str | None:
    if not is_button_click(event):
        return None
    if event.target.region_type == "tab_bar":
        return "click"
    # fieldid 后缀 _tab（含弹窗内页签）
    if (event.target.fieldid or "").endswith("_tab"):
        return "click"
    return None


def _recognize_toolbar_region(event: RecordedEvent) -> str | None:
    if event.target.region_type in ("top_action_bar", "table_action_bar") and is_button_click(event):
        return "click"
    return None


def _recognize_tree(event: RecordedEvent) -> str | None:
    if event.target.region_type == "tree" and event.type == "click":
        return "select"
    return None


def _recognize_query(event: RecordedEvent) -> str | None:
    if event.target.region_type != "query_box":
        return None
    if is_form_input(event):
        return "search"
    if is_button_click(event):
        label = (event.target.text or "").strip()
        if label == "查询":
            return "search"
        # ★ 查询区「重置」按钮 → query.reset（与 ydf-browser 0.1.16 对齐）
        if label == "重置":
            return "reset"
    return None


def _recognize_table_row_selection(event: RecordedEvent) -> str | None:
    # checkbox / switch change → select
    if (
        event.target.in_table
        and event.type == "change"
        and (
            event.target.role in ("checkbox", "switch")
            # ★ 原生 <input type="checkbox">/"radio" 没有 role 属性，
            #    需通过 input_type 或 fieldid 后缀识别
            or event.target.input_type in ("checkbox", "radio")
            or (event.target.fieldid or "").endswith("_checkbox")
        )
    ):
        return "select"
    # ★ WUI checkbox/switch click（span/div 带 role="checkbox"）→ select
    #   YonDiF WUI 框架用 span/div 包裹隐藏 input，点击事件在 wrapper 上触发
    if (
        event.target.in_table
        and event.type == "click"
        and not event.target.in_dialog
        and event.target.role in ("checkbox", "switch")
    ):
        return "select"
    # row click → select (ydf-browser supports row-click selection)
    # 仅匹配 tr/td 点击，排除 span/div（可能是表格区域内的按钮），
    # 避免"新增"等工具栏按钮被误判为行选择
    if (
        event.target.in_table
        and event.type == "click"
        and not event.target.in_dialog
        and (event.target.tag_name or "") in ("tr", "td")
        and not is_button_click(event)
        and (event.target.role or "") not in ("button", "link")
    ):
        return "select"
    return None


def _recognize_table_cell_link(event: RecordedEvent) -> str | None:
    # 表格单元格内的链接点击（a 标签或带 link 样式）
    if not event.target.in_table:
        return None
    if event.type != "click":
        return None
    tag = (event.target.tag_name or "").lower()
    if tag == "a":
        return "click_cell_link"
    # span/div 带 link 样式或 class 含 link
    if tag in ("span", "div") and event.target.text:
        cls = event.target.selector or ""
        if "link" in cls.lower():
            return "click_cell_link"
    return None


def _recognize_table_row_action(event: RecordedEvent) -> str | None:
    if event.target.in_table and is_button_click(event):
        if (event.target.text or "").strip() in _TABLE_ROW_ACTION_TEXTS:
            return "click"
    return None


def _recognize_editable_table_add_row(event: RecordedEvent) -> str | None:
    """识别可编辑表格的「增行」按钮。

    信号优先级：
    1. region_type == 'table_action_bar' 且按钮文本为「增行」/「新增」
    2. 任意位置点击「增行」按钮（强信号，无歧义）
    """
    if not is_button_click(event):
        return None
    label = (event.target.text or "").strip()
    if label == "增行":
        return "add_row"
    # 「新增」在表格工具栏区域 → add_row（而非 toolbar.click）
    if label == "新增" and event.target.region_type == "table_action_bar":
        return "add_row"
    return None


def _recognize_form(event: RecordedEvent) -> str | None:
    if event.target.region_type in ("content_card", None) and is_form_input(event):
        # ★ 排除表格内的 checkbox/radio — 这些由 table_row_selection 处理
        if event.target.in_table and event.target.input_type in ("checkbox", "radio"):
            return None
        if event.target.in_table and event.target.role in ("checkbox", "switch"):
            return None
        # ★ 文件选择框的 change 事件不是 fill：文件名由 converter 回填到
        #   前序 attachment.upload / import.upload 步骤（见 _enrich_upload_files）
        if event.target.input_type == "file":
            return None
        return "fill"
    return None


def _recognize_editable_table(event: RecordedEvent) -> str | None:
    # 表格内输入 → 明细表填行（含弹窗内明细表）；避免误进 form.fill（executor 排除表格字段）
    if event.target.in_table and is_form_input(event):
        # ★ 排除表头区域内的输入（列头筛选输入框），不作为可编辑表格单元格
        if event.target.in_table_header:
            return None
        # ★ 排除 checkbox/radio 的 input/change 事件 — 这些是行选择操作，
        #   已由 _recognize_table_row_selection 处理，不应产生 fill_row 步骤。
        #   浏览器在 checkbox 状态变更时会连续触发 change + input 事件，
        #   导致同一个 checkbox 点击产生两个步骤。
        if event.target.input_type in ("checkbox", "radio"):
            return None
        if event.target.role in ("checkbox", "switch"):
            return None
        # ★ 文件选择框不作为可编辑单元格填充
        if event.target.input_type == "file":
            return None
        return "fill_row"
    return None


def _recognize_toolbar_known(event: RecordedEvent) -> str | None:
    if is_button_click(event) and (event.target.text or "").strip() in _KNOWN_ACTION_LABELS:
        return "click"
    return None


def _recognize_toolbar_fallback(event: RecordedEvent) -> str | None:
    # 兜底：非弹窗内的按钮类点击归 toolbar.click（弹窗内按钮走 dialog/特定 handler）
    if not is_button_click(event) or event.target.in_dialog:
        return None
    # ★ 问题3修复：确定/确认/取消/关闭是弹窗按钮词汇。YonDiF 自定义弹窗
    #   可能不设置 in_dialog 标志，导致弹窗按钮落到这里被误判为 toolbar。
    #   真正的页面工具栏按钮由 region/known 路径识别，不会走到这里。
    label = (event.target.text or "").strip()
    if label in ("确定", "确认", "取消", "关闭", "OK", "Cancel"):
        return None
    return "click"


def _recognize_form_fallback(event: RecordedEvent) -> str | None:
    # 兜底：任何表单输入都归 form.fill
    if is_form_input(event):
        # ★ 排除表格表头区域内的输入（列头筛选输入框），不作为表单填充
        if event.target.in_table_header:
            return None
        # ★ 排除表格内的 checkbox/radio — 这些由 table_row_selection 处理
        #   但保留弹窗/表单中的 radio（如"上一岗"选择）作为 form.fill
        if event.target.in_table and event.target.input_type in ("checkbox", "radio"):
            return None
        if event.target.in_table and event.target.role in ("checkbox", "switch"):
            return None
        # ★ 文件选择框的 change 事件不是 fill（文件名由 converter 回填）
        if event.target.input_type == "file":
            return None
        return "fill"
    # ★ Switch 开关组件（如"是否金库退付"）不在表格内时归 form.fill
    #   YonDiF Switch 渲染为 div/span role="switch"，不是标准 input，
    #   is_form_input 不覆盖，需要单独识别
    if is_switch_toggle(event):
        return "fill"
    return None


def _recognize_form_switch(event: RecordedEvent) -> str | None:
    """识别 YDFSwitch / WUI Switch 开关组件的切换操作，归入 form.fill。

    YDFSwitch 渲染为 ``<button class="wui-switch">``，click 事件会被
    is_button_click / dialog handler 拦截，必须在它们之前识别。
    """
    if is_switch_toggle(event):
        return "fill"
    return None


# ── 注册表 ─────────────────────────────────────────────────

@dataclass(frozen=True)
class ComponentHandler:
    """单个单据组件的识别 + 构建契约。"""

    component: str
    recognize: HandlerRecognize


# 顺序即优先级。toolbar/form 各出现多次：region 命中在前，兜底在后，
# 中间夹着 tree/query/table，保证与原 classify_event 逐分支等价。
# ★ 新增组件按检测特异性从高到低插入：
#   notification/transfer_dialog（flag 检测，最特异）→ dialog 之前
#   action（fieldid/label 检测）→ toolbar region 之后、toolbar known 之前
#   amount_unit（flag 检测）→ form 之前
#   attachment/import（flag + text 检测）→ toolbar known 之前
HANDLERS: list[ComponentHandler] = [
    ComponentHandler("popup_reference", _recognize_popup_reference),
    ComponentHandler("notification", _recognize_notification_close),
    ComponentHandler("transfer_dialog", _recognize_transfer_dialog),
    # ★ P1-7：工作流批量结果层（flag 检测，最特异）—— 必须在 dialog 之前，
    #   否则结果层的「确认」会被 dialog handler 抢走
    ComponentHandler("workflow_result", _recognize_workflow_result),
    ComponentHandler("tab", _recognize_tab),
    # ★ Switch 必须在 dialog 之前：YDFSwitch 是 button tag，
    #   会被 dialog handler 误识别为弹窗按钮点击
    ComponentHandler("form", _recognize_form_switch),
    ComponentHandler("dialog", _recognize_dialog),
    ComponentHandler("toolbar", _recognize_toolbar_region),
    ComponentHandler("action", _recognize_action),
    ComponentHandler("tree", _recognize_tree),
    ComponentHandler("query", _recognize_query),
    ComponentHandler("table_row_selection", _recognize_table_row_selection),
    ComponentHandler("table", _recognize_table_cell_link),
    ComponentHandler("table_row_action", _recognize_table_row_action),
    ComponentHandler("amount_unit", _recognize_amount_unit),
    ComponentHandler("form", _recognize_form),
    ComponentHandler("editable_table", _recognize_editable_table_add_row),
    ComponentHandler("editable_table", _recognize_editable_table),
    ComponentHandler("attachment", _recognize_attachment_upload),
    ComponentHandler("import", _recognize_import_upload),
    ComponentHandler("import", _recognize_import_download_template),
    ComponentHandler("toolbar", _recognize_toolbar_known),
    ComponentHandler("toolbar", _recognize_toolbar_fallback),
    ComponentHandler("form", _recognize_form_fallback),
]


def classify_event(event: RecordedEvent) -> tuple[str, str] | None:
    """将单个录制事件映射为 ``(component, operation)``，无映射时返回 None。

    navigation / dialog_open / dialog_close / hover 不产生组件步骤（由上层
    open_menu / 合并阶段处理）。checkpoint 在入口处直接分流（见上）。
    """
    if event.type in ("navigation", "dialog_open", "dialog_close", "hover"):
        return None
    # ★ 断言检查点（Alt+点击录制）：按目标位置分流到对应 assert 步骤
    if event.type == "checkpoint":
        t = event.target
        if t.is_notification_close or t.notification_text:
            return ("notification", "assert")
        if t.in_table and (t.row_data or (t.cell_text and t.column_header)):
            return ("table", "assert_row_values")
        # ★ P1-7：结果层检查点 → 统计断言（回放端要求至少一个统计字段）
        if t.is_workflow_result and _parse_workflow_counts(
            t.workflow_result_text or t.text or ""
        ):
            return ("workflow_result", "assert")
        return ("form", "assert_values")
    for handler in HANDLERS:
        operation = handler.recognize(event)
        if operation is not None:
            return (handler.component, operation)
    return None


def build_target(
    component: str,
    operation: str,
    events: list[RecordedEvent],
) -> dict[str, Any]:
    """根据 component.operation 和原始事件构建 target dict。"""
    # add_row 是 editable_table 的特殊 operation，用专用 builder
    if component == "editable_table" and operation == "add_row":
        return _build_editable_table_add_row(operation, events)
    # 断言步骤用专用 builder（与普通 fill/click 的 target 结构不同）
    if component == "form" and operation == "assert_values":
        return _build_form_assert(operation, events)
    if component == "table" and operation == "assert_row_values":
        return _build_table_assert(operation, events)
    # import 有两个 operation，用各自的 builder
    if component == "import" and operation == "download_template":
        return _build_import_download_template(operation, events)
    # query.reset 的 target 恒为空对象（与 ydf-browser 0.1.16 queryResetTarget 对齐）
    if component == "query" and operation == "reset":
        return {}
    builder = _BUILDERS.get(component)
    if builder is None:
        return {}
    return builder(operation, events)


def can_coalesce(
    a_pair: tuple[str, str],
    b_pair: tuple[str, str],
    a_event: RecordedEvent,
    b_event: RecordedEvent,
) -> bool:
    """两个 ``(component, operation)`` 是否可合并为单个 step。

    ``editable_table.fill_row`` 额外要求同表同行才合并（避免跨行混填）。
    ``form.fill`` 额外要求同一弹窗上下文才合并（避免跨弹窗覆盖）。
    """
    if a_pair != b_pair or a_pair not in _COALESCEABLE_PAIRS:
        return False
    if a_pair in (("dialog", "confirm"), ("dialog", "cancel")):
        # ★ 弹窗按钮去重：仅合并同一物理按钮的重复点击（mousedown+click 双发），
        #   不同 fid 的确定（选择器 *_modal_ok 与外层 qd_btn）保持独立步骤
        a_fid = (a_event.target.fieldid or "").strip()
        b_fid = (b_event.target.fieldid or "").strip()
        return bool(a_fid) and a_fid == b_fid
    if a_pair == ("editable_table", "fill_row"):
        # 优先用 inject JS 设置的 editable_row_number / editable_table_name
        a_row = a_event.target.editable_row_number
        b_row = b_event.target.editable_row_number
        a_table = a_event.target.editable_table_name or ""
        b_table = b_event.target.editable_table_name or ""
        # 如果 inject JS 没采集到，回退到 fieldid 解析
        if a_row is None:
            a_parsed = _parse_editable_fieldid(a_event.target.fieldid)
            if a_parsed:
                a_row = a_parsed[2]
                if not a_table:
                    a_table = a_parsed[0]
        if b_row is None:
            b_parsed = _parse_editable_fieldid(b_event.target.fieldid)
            if b_parsed:
                b_row = b_parsed[2]
                if not b_table:
                    b_table = b_parsed[0]
        return (
            a_row is not None
            and a_row == b_row
            and a_table == b_table
        )
    if a_pair == ("form", "fill"):
        # ★ form.fill 跨弹窗上下文不合并：
        #   用户先填主表单 → 打开弹窗操作 → 关闭弹窗后继续填主表单，
        #   弹窗前后的 form.fill 不应合并（会覆盖前面的字段值）。
        #   判断依据：两个事件的 in_dialog 状态必须一致。
        if a_event.target.in_dialog != b_event.target.in_dialog:
            return False
        # ★ 跨 URL 页面不合并（如主表单 vs 弹窗内的独立页面）
        a_url = a_event.context.url or ""
        b_url = b_event.context.url or ""
        if a_url and b_url and a_url != b_url:
            return False
        # ★ 跨页签不合并（问题2修复）：用户填 A 页签 → 切到 B 页签再填，
        #   两侧的 form.fill 属于不同表单。若切换动作未被识别成步骤
        #   （classify 为 None 被丢弃），此护栏防止两侧 fill 合并成一步
        #   导致后填字段覆盖先填字段、页签切换丢失。
        a_tab = a_event.context.active_tab or ""
        b_tab = b_event.context.active_tab or ""
        if a_tab != b_tab:
            return False
        # ★ 跨弹窗标题不合并（问题2修复）：同一 URL 下两个弹窗表单
        #   （如向导式两步表单），dialog_title 变化即为表单边界。
        a_dt = a_event.context.dialog_title or ""
        b_dt = b_event.context.dialog_title or ""
        if a_dt != b_dt:
            return False
    return True
