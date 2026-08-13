"""录制事件 → DSL YAML 转换器（与 ydf-browser 解耦）。

将 ``RecordedEvent`` 序列转换为符合 ydf-browser DSL 规范的 YAML 测试套件。
组件识别与 target 构建委托 ``registry``（单据组件处理器注册表）；
文档模型使用 recorder 自有的 ``dsl_models``，**不 import 任何 ydf_browser 模块**。

核心流程：
  1. 语义分类：``registry.classify_event`` → ``(component, operation)``
  2. 动作合并：连续可合并事件归为单个 step
  3. target 构建：``registry.build_target``
  4. 输出：``dsl_models`` → YAML 字符串
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from .dsl_models import DslDocument, DslTestCase, DslTestSuite
from .models import RecordedEvent, RecordedEventTarget, RecordingSession
# classify_event / build_target / can_coalesce 的实现来自 registry；
# 此处 re-export 以保持 ``from .converter import classify_event`` 等公开 API。
from .registry import build_target, can_coalesce, classify_event

__all__ = [
    "abstract_values",
    "build_dsl_document",
    "build_target",
    "classify_event",
    "coalesce_events",
    "convert_events_to_steps",
    "dsl_to_yaml",
    "extract_menu_path",
    "inject_captures",
    "load_events_from_json",
    "load_events_from_jsonl",
]


# ── 动作合并 ──────────────────────────────────────────────

def coalesce_events(
    events: list[RecordedEvent],
    classifications: list[tuple[str, str] | None],
) -> list[tuple[tuple[str, str], list[RecordedEvent]]]:
    """将连续可合并的事件分组。

    Returns:
        ``[((component, operation), [events]), ...]``
    """
    groups: list[tuple[tuple[str, str], list[RecordedEvent]]] = []
    for event, cls in zip(events, classifications):
        if cls is None:
            continue
        if groups and can_coalesce(groups[-1][0], cls, groups[-1][1][-1], event):
            groups[-1][1].append(event)
        else:
            groups.append((cls, [event]))
    return groups


# ── 变量值抽象 ─────────────────────────────────────────────

_ABSTRACT_PATTERNS = [
    (re.compile(r"^\d{17}[\dXx]$"), "{{random.id_card}}"),       # 18位身份证
    (re.compile(r"^1[3-9]\d{9}$"), "{{random.mobile}}"),         # 手机号
    (re.compile(r"^\d{16,19}$"), "{{random.bank_card}}"),        # 银行卡号
    (re.compile(r"^\d{4}-\d{2}-\d{2}"), "{{random.date}}"),      # 日期
    (re.compile(r"^\d{10,13}$"), "{{random.timestamp}}"),        # 时间戳
    (re.compile(r"^\d{6,}$"), "{{random.suffix}}"),              # 长数字
]


def _maybe_abstract_value(value: str) -> str:
    """尝试将值抽象为 ``{{random.*}}`` 变量。"""
    value = value.strip()
    for pattern, replacement in _ABSTRACT_PATTERNS:
        if pattern.fullmatch(value):
            return replacement
    return value


def abstract_values(target: dict[str, Any]) -> dict[str, Any]:
    """递归替换 target 中的硬编码值为 ``{{random.*}}`` 变量。"""
    result: dict[str, Any] = {}
    for key, val in target.items():
        if isinstance(val, str):
            result[key] = _maybe_abstract_value(val)
        elif isinstance(val, dict):
            result[key] = abstract_values(val)
        elif isinstance(val, list):
            result[key] = [
                abstract_values(item) if isinstance(item, dict)
                else _maybe_abstract_value(item) if isinstance(item, str)
                else item
                for item in val
            ]
        else:
            result[key] = val
    return result


# ── 主转换 ─────────────────────────────────────────────────

# 已知工具栏动作集合 — 用于 extract_popup_reference 中阻止误消费
_TOOLBAR_ACTION_SET = frozenset(
    {"保存", "提交", "删除", "新增", "增行", "删行", "导出", "导入", "审核", "弃审", "打印",
     "确定", "确认", "取消", "关闭", "返回"}
)


def extract_popup_reference(
    events: list[RecordedEvent],
) -> tuple[list[RecordedEvent], list[RecordedEvent]]:
    """把参照弹窗内的「选行 → 确定」聚合成合成事件。

    基于 ``is_popup_reference=True`` 的连续事件段识别——**不依赖 dialog_open
    的 choice-surface 判定**，因为弹窗刚打开时表格可能尚未渲染，dialog_open
    探测会漏报（实测：dialog_open 时 popup=0，但弹窗内 click 时 popup=1）。

    仅当段内**纯 click 选行（无 input/change 编辑）且有 cell_text 证据**时才
    判定为参照选择，避免把「弹窗内明细表填值」误判为参照选择。
    """
    consumed: set[int] = set()
    synthetic: list[RecordedEvent] = []

    i = 0
    while i < len(events):
        if not events[i].target.is_popup_reference:
            i += 1
            continue
        j = i
        title: str | None = None
        selected: tuple[str | None, str | None, str | None] | None = None
        has_input = False
        while j < len(events) and events[j].target.is_popup_reference:
            ej = events[j]
            # ★ 遇到已知工具栏动作（保存/提交/删除等）时停止扫描，
            # 即使 is_popup_reference=True（日期弹窗可能未正确关闭）
            ej_text = (ej.target.text or "").strip()
            if ej.type == "click" and ej_text in _TOOLBAR_ACTION_SET:
                break
            if ej.type in ("input", "change"):
                has_input = True
            if title is None:
                title = ej.target.popup_title or ej.context.dialog_title
            if selected is None and ej.target.cell_text:
                selected = (ej.target.cell_text, ej.target.column_header, ej.target.row_text)
            j += 1
        if selected is not None and not has_input:
            for k in range(i, j):
                consumed.add(k)
            synthetic.append(_make_popup_synthetic(events[i], title, selected))
        # ★ 防止死循环：如果内层 while 在 j==i 时就 break（如第一个事件是工具栏动作），
        # i 必须前进至少 1
        i = max(j, i + 1)

    remaining = [e for idx, e in enumerate(events) if idx not in consumed]
    return remaining, synthetic


def _make_popup_synthetic(
    anchor_ev: RecordedEvent,
    title: str | None,
    selected: tuple[str | None, str | None, str | None],
) -> RecordedEvent:
    cell_text, column_header, row_text = selected
    return RecordedEvent(
        seq=anchor_ev.seq,
        timestamp=anchor_ev.timestamp,
        type="popup_reference_select",
        target=RecordedEventTarget(
            popup_title=title,
            cell_text=cell_text,
            column_header=column_header,
            row_text=row_text,
            text=cell_text or row_text,
            in_dialog=True,
            is_popup_reference=True,
        ),
        context=anchor_ev.context,
        meta=anchor_ev.meta,
    )


def convert_events_to_steps(
    events: list[RecordedEvent],
    abstract: bool = False,
    auto_capture: bool = False,
) -> list[dict[str, Any]]:
    """将录制事件列表转换为 DSL 步骤 dict 列表。

    Args:
        events: 录制事件列表。
        abstract: 是否自动将硬编码值抽象为 ``{{random.*}}`` 变量。
        auto_capture: 是否自动注入 capture 步骤（form.capture_values / table.capture_row_values）。

    Returns:
        DSL 步骤 dict 列表（可直接序列化为 YAML）。
    """
    # 预处理：将「点击表单参照字段 → 选择树节点」转为合成的 form change 事件，
    # 并过滤表单输入框的聚焦点击
    events = _preprocess_form_interactions(events)

    # 预处理（兜底）：处理 Pattern 5 未捕获的弹窗选择器项点击
    # （表单字段缺少 label_text 时，从 popup item 反向查找 form field）
    events = _preprocess_popup_selector_fallback(events)

    # 预处理：将「hover 工具栏下拉按钮 → click 下拉子项」合成带 sub_label 的 toolbar click
    events = _preprocess_hover_dropdown(events)

    # 预处理：将可编辑表格参照字段的弹窗交互合成为结构化值
    events = _preprocess_editable_table_references(events)

    # 先聚合参照弹窗生命周期，合成事件按 seq 回插原序
    remaining, popup_synthetic = extract_popup_reference(events)
    merged = sorted(remaining + popup_synthetic, key=lambda e: e.seq)

    classifications = [classify_event(e) for e in merged]
    groups = coalesce_events(merged, classifications)

    steps: list[dict[str, Any]] = []
    for (component, operation), group_events in groups:
        target = build_target(component, operation, group_events)
        if abstract:
            target = abstract_values(target)
        step: dict[str, Any] = {"component": component, "operation": operation}
        if target:
            step["target"] = target
        steps.append(step)
    steps = [s for s in steps if not _is_noise_step(s)]
    steps = _merge_form_fills(steps)
    steps = _filter_redundant_tree_popup(steps)
    steps = _dedup_editable_table_fills(steps)
    steps = _merge_toolbar_sub_labels(steps)
    steps = _deduplicate_steps(steps)
    if auto_capture:
        steps = _inject_captures(steps)
    return steps


# 弹窗内不应被识别为"选择项"的按钮标签（工具栏动作 + 弹窗确认/取消）
_FORM_POPUP_BUTTON_LABELS = frozenset({
    # 工具栏动作
    "新增", "删除", "保存", "提交", "编辑", "详情", "导入", "导出",
    "打印", "审核", "弃审", "取消", "返回", "确定", "确认", "查询",
    "重置", "增行", "删行", "更多", "关闭", "刷新",
    # 弹窗确认/取消
    "OK", "Yes", "No", "Cancel", "是", "否",
})


def _preprocess_form_interactions(
    events: list[RecordedEvent],
) -> list[RecordedEvent]:
    """预处理表单交互事件：参照选择合成 + 聚焦点击过滤 + 下拉/日期选择合成。

    YonDiF 表单中的字段通过多种交互模式完成：
    1. **参照字段**：点击搜索输入框 → 点击树节点（region_type=tree）
    2. **下拉选择**：点击 *_search_input → 点击 *_option_* div（如票据类型）
    3. **日期选择**：点击 *_suffix span → 点击日历单元格（cell_text 是日期）
    4. **直接输入**：点击 input/textarea → input/change 事件
    5. **弹窗选择器**：点击表单字段 → 弹出选择器 → 点击一个项（非 tree/option/date）→ 可选点「确定」确认

    此函数将模式 1-3、5 合成 ``change`` 事件（归入 form.fill），
    模式 4 过滤聚焦点击（避免被误分类为 dialog.click）。
    """
    result: list[RecordedEvent] = []
    consumed: set[int] = set()

    for i, e in enumerate(events):
        if i in consumed:
            continue

        # ── 模式检测：点击表单字段（在弹窗内，非表格，有 label_text）──
        if (
            e.type == "click"
            and e.target.in_dialog
            and not e.target.in_table
            and e.target.tag_name in ("input", "div", "span")
            and e.target.label_text
        ):
            label = e.target.label_text
            fieldid = e.target.fieldid or ""
            # ★ 提取 widget 前缀用于识别同一组件的子元素点击
            # 如 xxx_suffix → xxx，xxx_search_input → xxx
            widget_prefix = re.sub(r"_(?:suffix|search_input)$", "", fieldid)

            # ★ 跟踪 i 和 j 之间需要消费的事件（重复点击、switcher 点击等）
            between_consumed: set[int] = set()

            # ★ 向前看 1-8 个事件（增大范围以容纳重复点击和 late change）
            for j in range(i + 1, min(i + 9, len(events))):
                ej = events[j]
                ej_text = (ej.target.text or "").strip()
                ej_label = (ej.target.label_text or "").strip()
                ej_fid = ej.target.fieldid or ""

                # ★ 跳过同字段重复点击（如 _search_input 被点两次）
                if ej.type == "click" and ej_fid == fieldid:
                    between_consumed.add(j)
                    continue

                # ★ 跳过 tree switcher 点击（region=tree 但无文本，是展开/折叠按钮）
                if (
                    ej.type == "click"
                    and ej.target.region_type == "tree"
                    and not (ej_text or ej_label)
                ):
                    between_consumed.add(j)
                    continue

                # ★ 跳过日期选择器导航按钮（_next_btn, _prev_btn, _today_btn）
                if (
                    ej.type == "click"
                    and widget_prefix
                    and ej_fid
                    and ej_fid.startswith(widget_prefix)
                    and any(s in ej_fid for s in ("_next_btn", "_prev_btn", "_today_btn"))
                ):
                    between_consumed.add(j)
                    continue

                # ★ 跳过其他字段的 late change/input（延迟到达的前一字段变更）
                if ej.type in ("input", "change") and ej_fid != fieldid:
                    continue  # 不消费，仅跳过

                # ── 模式 1: tree.select → 参照选择 ──
                if (
                    ej.type == "click"
                    and ej.target.region_type == "tree"
                    and (ej_text or ej_label)
                ):
                    value = ej_text or ej_label
                    result.append(_make_form_change(e, label, value))
                    consumed.add(i)
                    consumed.add(j)
                    consumed.update(between_consumed)
                    # ★ 消费后续重复的 tree click（相同文本）
                    for k in range(j + 1, min(j + 4, len(events))):
                        ek = events[k]
                        ek_text = (ek.target.text or "").strip()
                        ek_label = (ek.target.label_text or "").strip()
                        if ek.type == "click" and (ek_text == ej_text or ek_label == ej_label):
                            consumed.add(k)
                        elif ek.type != "click":
                            break
                    break

                # ── 模式 2: 下拉选项点击（fieldid 含 _option_）──
                if (
                    ej.type == "click"
                    and "_option_" in ej_fid
                    and (ej_text or ej_label)
                ):
                    # ★ 优先用选项文本；如果 ej_text 为空但 ej_label 看起来像字段标签（如"款项类型"），跳过
                    # 避免 "款项类型: 款项类型" 的 bug
                    if not ej_text and ej_label:
                        # 检查 ej_label 是否看起来像字段标签（而非选项文本）
                        # 选项文本通常不会等于字段标签
                        if ej_label == label:
                            break  # ej_label 就是字段标签，ej_text 为空，跳过
                    value = ej_text or ej_label
                    result.append(_make_form_change(e, label, value))
                    consumed.add(i)
                    consumed.add(j)
                    consumed.update(between_consumed)
                    # ★ 消费后续重复的 option click（同一 fieldid）
                    for k in range(j + 1, min(j + 4, len(events))):
                        ek = events[k]
                        if ek.type == "click" and ek.target.fieldid == ej_fid:
                            consumed.add(k)
                        elif ek.type != "click":
                            break
                    break

                # ── 模式 3: 日期选择（点击日历单元格，cell_text 是日期格式）──
                if (
                    ej.type == "click"
                    and ej.target.cell_text
                    and re.match(r"^\d{4}-\d{2}-\d{2}", ej.target.cell_text)
                ):
                    result.append(_make_form_change(e, label, ej.target.cell_text))
                    consumed.add(i)
                    consumed.add(j)
                    consumed.update(between_consumed)
                    # ★ 消费后续重复的日历单元格点击
                    for k in range(j + 1, min(j + 4, len(events))):
                        ek = events[k]
                        if (
                            ek.type == "click"
                            and ek.target.cell_text
                            and re.match(r"^\d{4}-\d{2}-\d{2}", ek.target.cell_text or "")
                            and ek.target.cell_text == ej.target.cell_text
                        ):
                            consumed.add(k)
                        elif ek.type != "click":
                            break
                    break

                # 如果遇到同字段的 input/change，说明不是选择模式而是直接输入
                if (
                    ej.type in ("input", "change")
                    and ej.target.fieldid == fieldid
                ):
                    break
                # ── 模式 5: 弹窗选择器项点击（非 tree/option/date 的弹窗内点击）──
                # 用户点击表单字段 → 弹出选择器 → 点击一个项 → 可选点「确定」确认
                # 这种模式在 YonDiF 的组织选择、项目选择等场景中很常见
                if ej.type == "click" and ej.target.region_type != "tree" and "_option_" not in ej_fid:
                    # 日历单元格可能 tag=div 且 in_table=True，不中止
                    if not (ej.target.cell_text and re.match(r"^\d{4}-\d{2}-\d{2}", ej.target.cell_text)):
                        # ★ 检查是否是弹窗选择器项（非按钮类点击，有文本，不在已知按钮标签集合中）
                        ej_text_clean = (ej.target.text or "").strip()
                        is_popup_item = (
                            ej.target.in_dialog
                            and (ej_text or ej_label)
                            and ej_text_clean not in _FORM_POPUP_BUTTON_LABELS
                        )
                        if is_popup_item:
                            value = ej_text or ej_label
                            # 向前看 1-6 个事件，查找「确定」按钮
                            # 同时消费中间的更多 popup item 点击（多级树选择）
                            confirm_consumed: set[int] = set()
                            last_value = value
                            for k in range(j + 1, min(j + 7, len(events))):
                                ek = events[k]
                                ek_text = (ek.target.text or "").strip()
                                if ek.type == "click" and ek_text in ("确定", "确认", "OK", "是"):
                                    confirm_consumed.add(k)
                                    break
                                # 消费更多 popup item 点击（非按钮标签）
                                ek_label_k = (ek.target.label_text or "").strip()
                                if (
                                    ek.type == "click"
                                    and (ek_text or ek_label_k)
                                    and ek_text not in _FORM_POPUP_BUTTON_LABELS
                                ):
                                    confirm_consumed.add(k)
                                    last_value = ek_text or ek_label_k
                                    continue
                                # 遇到非 click 事件，中止查找
                                if ek.type != "click":
                                    break
                            result.append(_make_form_change(e, label, last_value))
                            consumed.add(i)
                            consumed.add(j)
                            consumed.update(between_consumed)
                            consumed.update(confirm_consumed)
                            break
                        # 不是弹窗选择器项，中止
                        break

        if i in consumed:
            continue

        # ── 过滤重复的下拉选项点击（如 票据类型 option 被点击两次）──
        if (
            e.type == "click"
            and "_option_" in (e.target.fieldid or "")
        ):
            # 检查后续 1-3 个事件是否有同 fieldid 的重复 click
            for j in range(i + 1, min(i + 4, len(events))):
                ej = events[j]
                if ej.type == "click" and ej.target.fieldid == e.target.fieldid:
                    consumed.add(i)  # 保留第二次（它有 label_text），过滤第一次
                    break
                if ej.type != "click":
                    break

        if i in consumed:
            continue

        # ── 模式 4: 过滤纯聚焦点击 ──
        # click on input/textarea/span(suffix) 后跟同字段的 input/change
        if (
            e.type == "click"
            and e.target.in_dialog
            and not e.target.in_table
            and e.target.tag_name in ("input", "textarea", "select", "span")
            and e.target.fieldid
        ):
            # 检查后续 1-3 个事件是否有同字段的 input/change
            for j in range(i + 1, min(i + 4, len(events))):
                ej = events[j]
                if (
                    ej.type in ("input", "change")
                    and ej.target.fieldid == e.target.fieldid
                ):
                    consumed.add(i)  # 过滤掉聚焦点击
                    break
                # 同 fieldid 的重复 click 也跳过
                if ej.type == "click" and ej.target.fieldid == e.target.fieldid:
                    consumed.add(i)
                    break
                if ej.type == "click" and ej.target.fieldid != e.target.fieldid:
                    break

        if i in consumed:
            continue

        result.append(e)

    return result


def _preprocess_popup_selector_fallback(
    events: list[RecordedEvent],
) -> list[RecordedEvent]:
    """处理未被 ``_preprocess_form_interactions`` 捕获的弹窗选择器项点击。

    当表单字段点击缺少 ``label_text``（或字段点击本身被 Pattern 4 过滤、
    或字段是 ``button`` 标签）时，Pattern 5 不会触发。此函数从 **popup item
    点击**出发，向前查找「确定」按钮、向后反查 form field 点击来获取标签，
    最终合成为 ``form.change`` 事件。

    检测条件（同时满足）：
    - 弹窗内点击，有文本，不在表格内
    - 文本不在 ``_FORM_POPUP_BUTTON_LABELS`` 集合中（不是按钮）
    - 不在 tree / reference / transfer 区域（由其他模式处理）
    - fieldid 不含 ``_option_``（由 Pattern 2 处理）
    - 后续 1-5 个事件内有「确定/确认」按钮
    """
    result: list[RecordedEvent] = []
    consumed: set[int] = set()

    for i, e in enumerate(events):
        if i in consumed:
            continue

        e_text = (e.target.text or "").strip()

        # ── 检测：弹窗内的非按钮类点击 ──
        if not (
            e.type == "click"
            and e.target.in_dialog
            and not e.target.in_table
            and e_text
            and e_text not in _FORM_POPUP_BUTTON_LABELS
            and e.target.region_type != "tree"
            and not e.target.is_popup_reference
            and not e.target.is_transfer_item
            and "_option_" not in (e.target.fieldid or "")
        ):
            result.append(e)
            continue

        # ── 向前看 1-5 个事件，查找「确定」按钮 ──
        confirm_idx: int | None = None
        extra_consumed: set[int] = set()
        last_value = e_text

        for j in range(i + 1, min(i + 6, len(events))):
            ej = events[j]
            ej_text = (ej.target.text or "").strip()
            if ej.type == "click" and ej_text in ("确定", "确认", "OK", "是"):
                confirm_idx = j
                break
            # 消费更多 popup item 点击（非按钮标签）
            if (
                ej.type == "click"
                and ej_text
                and ej_text not in _FORM_POPUP_BUTTON_LABELS
            ):
                extra_consumed.add(j)
                last_value = ej_text
                continue
            # 非点击事件 → 中止
            if ej.type != "click":
                break

        if confirm_idx is None:
            # 没有「确定」按钮，不是弹窗选择器模式 → 保留原事件
            result.append(e)
            continue

        # ── 向后看 1-5 个事件，反查 form field 点击获取标签 ──
        label = ""
        field_anchor: int | None = None
        for k in range(i - 1, max(i - 6, -1), -1):
            ek = events[k]
            if k in consumed:
                continue
            if (
                ek.type == "click"
                and ek.target.in_dialog
                and not ek.target.in_table
                and ek.target.tag_name in ("input", "div", "span", "button")
            ):
                # 优先用 label_text，其次 placeholder / aria_label
                label = (
                    ek.target.label_text
                    or ek.target.placeholder
                    or ek.target.aria_label
                    or ""
                ).strip()
                if label and label not in _FORM_POPUP_BUTTON_LABELS:
                    field_anchor = k
                else:
                    label = ""
                break
            # 非点击事件 → 中止反查
            if ek.type != "click":
                break

        # 如果找不到 form field 点击，用 popup item 的文本作为 label
        if not label:
            label = last_value

        # ── 合成 form.change ──
        result.append(_make_form_change(e, label, last_value))
        consumed.add(i)
        consumed.add(confirm_idx)
        consumed.update(extra_consumed)
        if field_anchor is not None:
            consumed.add(field_anchor)

    return result


def _make_form_change(
    anchor_ev: RecordedEvent,
    label: str,
    value: str,
) -> RecordedEvent:
    """合成表单 change 事件。"""
    return RecordedEvent(
        seq=anchor_ev.seq,
        timestamp=anchor_ev.timestamp,
        type="change",
        target=RecordedEventTarget(
            fieldid=anchor_ev.target.fieldid,
            label_text=label,
            tag_name="input",
            in_dialog=True,
            region_type="dialog_page",
            value=value,
            display_text=value,
        ),
        context=anchor_ev.context,
        meta=anchor_ev.meta,
    )


# YonDiF 工具栏已知动作词，按长度降序排列以便优先匹配长词
_KNOWN_TOOLBAR_ACTIONS = [
    "增值税发票", "弃审", "审核", "导入", "导出", "新增", "提交",
    "删除", "保存", "打印", "更多", "关闭", "取消", "刷新", "查询",
]


def _extract_first_action(label: str) -> str:
    """如果 label 是多个已知工具栏动作词的拼接，返回第一个。

    例如 "新增提交删除" → "新增"，"保存提交" → "保存"。
    如果 label 不是拼接的动作词，原样返回。
    """
    if not label or len(label) <= 4:
        return label
    # 尝试从头匹配已知动作词
    for action in _KNOWN_TOOLBAR_ACTIONS:
        if label.startswith(action):
            remaining = label[len(action):]
            if not remaining:
                return label  # 只有一个动作词，原样返回
            # 检查剩余部分是否也是已知动作词的拼接
            for action2 in _KNOWN_TOOLBAR_ACTIONS:
                if remaining.startswith(action2):
                    # 至少两个动作词拼接 → 返回第一个
                    return action
            return label  # 剩余部分不是已知动作词，原样返回
    return label


def _preprocess_hover_dropdown(
    events: list[RecordedEvent],
) -> list[RecordedEvent]:
    """预处理 hover 触发的下拉菜单操作：hover → click 合成。

    YonDiF 工具栏的"新增"是悬浮触发下拉按钮。用户操作流程：
    1. 鼠标悬浮到"新增"按钮 → 下拉菜单展开（产生 hover 事件）
    2. 鼠标移动到下拉子项（可能扫过"提交""删除"等，产生更多 hover 事件）
    3. 点击下拉菜单中的子项（如"增值税发票开票申请"）（产生 click 事件）

    此函数检测连续 hover 事件后的 click 事件：
    - 用**第一个** hover 的文本作为 toolbar label（那是真正触发下拉的按钮）
    - click 的文本作为 sub_label
    - 中间的 hover 事件（鼠标扫过的其他按钮）全部丢弃
    - 未匹配到 click 的 hover 事件也全部丢弃（纯鼠标移动噪声）
    """
    result: list[RecordedEvent] = []
    consumed: set[int] = set()

    for i, e in enumerate(events):
        if i in consumed:
            continue

        # 检测 hover 事件
        if e.type == "hover" and e.target.region_type == "top_action_bar":
            hover_label = (e.target.text or "").strip()
            # ★ 兜底：即使 JS 端仍抓到拼接文本（"新增提交删除"），
            # 也拆分出第一个动作词
            hover_label = _extract_first_action(hover_label)
            # 收集这组连续 hover 的索引（鼠标可能扫过多个按钮）
            hover_indices = [i]

            # 向前看 1-8 个事件，搜索紧随其后的 click
            # 跳过中间的 hover 事件（鼠标移动噪声），只找 click
            for j in range(i + 1, min(i + 9, len(events))):
                ej = events[j]
                if ej.type == "hover":
                    # 中间的 hover 事件，记录但不中止搜索
                    hover_indices.append(j)
                    continue
                if ej.type == "click":
                    click_label = (ej.target.text or "").strip()
                    # ★ 也对 click_label 做动作词拆分
                    click_label_extracted = _extract_first_action(click_label)
                    # 如果 click 的文本和第一个 hover 的文本不同 → 是下拉子项
                    # ★ 额外检查：如果 click 和 hover 在同一个 fieldid（如 main_toolbar），
                    # 或者 click_label 拆分后 == hover_label，说明是容器点击而非子项选择
                    is_same_container = (
                        ej.target.fieldid == e.target.fieldid
                        and ej.target.fieldid is not None
                    )
                    # ★ 额外检查：如果 click 目标也在 top_action_bar 区域，
                    # 说明它是另一个工具栏按钮（如"审核"和"退回"是同级按钮），
                    # 不是下拉菜单的子项。下拉子项通常在 popup/menu 区域。
                    is_sibling_toolbar_btn = (
                        ej.target.region_type == "top_action_bar"
                    )
                    if (
                        click_label
                        and click_label_extracted != hover_label
                        and not is_same_container
                        and not is_sibling_toolbar_btn
                    ):
                        # 合成为 toolbar click 事件
                        synthetic = RecordedEvent(
                            seq=e.seq,
                            timestamp=e.timestamp,
                            type="click",
                            target=RecordedEventTarget(
                                fieldid=e.target.fieldid,
                                label_text=hover_label,
                                text=hover_label,
                                tag_name=e.target.tag_name,
                                in_dialog=False,
                                in_table=False,
                                region_type="top_action_bar",
                                # 用 display_text 携带 sub_label 信息
                                display_text=click_label,
                            ),
                            context=e.context,
                            meta=e.meta,
                        )
                        result.append(synthetic)
                        # 消费所有 hover 和 click
                        for hi in hover_indices:
                            consumed.add(hi)
                        consumed.add(j)
                    break
                # 其他类型事件（input/change 等）中止搜索
                break

        if i in consumed:
            continue

        # ★ 丢弃未匹配到 click 的 hover 事件（纯鼠标移动噪声）
        if e.type == "hover":
            continue

        # ★ 过滤工具栏容器点击：fieldid=main_toolbar 且文本是拼接的动作词
        # （如 "新增提交删除"），说明用户点了容器而非具体按钮
        if (
            e.type == "click"
            and e.target.fieldid == "main_toolbar"
            and _extract_first_action((e.target.text or "").strip()) != (e.target.text or "").strip()
        ):
            continue

        result.append(e)

    return result


def _looks_like_wrong_metadata(value: str | None, fieldid: str | None) -> bool:
    """判断 JS 注入的 editable_column / editable_table_name 是否明显错误。

    YonDiF 的 JS 注入经常把表格的第一列表头（如 "序号"）误提取为表名或列名。
    本函数检测这类常见错误：
    - "序号" — 几乎总是表格的第一列，不是表名也不是参照列名
    - 纯数字 — fieldid 解析出的 dataField ID，不是中文标签
    - 值与 fieldid 中的 column 部分完全不匹配
    """
    if not value:
        return False
    if value == "序号":
        return True
    if value.isdigit():
        return True
    return False


def _parse_editable_fieldid_safe(fid: str | None) -> tuple[str, str, int] | None:
    """从 fieldid 解析可编辑单元格的 ``(table, column, row_number)``。

    遵循 ydf 规则 ``<tableFieldid>_<dataField>_<rowIndex>``（rowIndex 0-based）。
    支持带 ``_btn_i`` / ``_btn`` 后缀的参照触发器 fieldid（先剥离后缀再解析）。

    ★ 使用贪婪首组 ``(.+)`` 以正确拆分多下划线表名：
    ``plzf_skrxx_table_productNameShow_0`` → (``plzf_skrxx_table``, ``productNameShow``, 1)
    而非 (``plzf``, ``skrxx_table_productNameShow``, 1)。
    """
    if not fid:
        return None
    # 剥离参照触发器后缀：plzf_skrxx_table_productNameShow_0_btn_i → plzf_skrxx_table_productNameShow_0
    cleaned = re.sub(r"_(?:btn(?:_i|_icon)?)$", "", fid)
    match = re.match(r"^(.+)_(.+?)_(\d+)$", cleaned)
    if not match:
        return None
    return (match.group(1), match.group(2), int(match.group(3)) + 1)


def _preprocess_editable_table_references(
    events: list[RecordedEvent],
) -> list[RecordedEvent]:
    """预处理可编辑表格中的参照字段交互。

    当用户在可编辑表格中点击参照字段单元格时（如"商品"列）：
    1. 点击单元格（in_table=True）
    2. 弹出参照弹窗
    3. 在弹窗中输入筛选条件
    4. 点击选择一行
    5. 点击"确定"确认
    6. 弹窗关闭，单元格回填

    此函数将这组事件合成为一个 change 事件，其 structured_value 为：
    ``{filter: "筛选文本", match: {column: "列名", equals: "值"}}``

    ★ 核心策略：范围消费。从单元格点击开始，到遇到"终止条件"为止，
    范围内的所有事件（input/click/dialog_open/dialog_close/确定/取消等）
    都被视为弹窗交互的一部分，被全部消费。

    终止条件：
    - 页面级工具栏按钮（保存/提交/删除/新增/增行/删行，且不在弹窗内）
    - 下一个可编辑表格单元格点击（不在弹窗内）
    - 扫描范围上限（20个事件）

    不再依赖 in_dialog/is_popup_reference 标志判断，
    因为 YonDiF 弹窗可能使用自定义容器类，这些标志可能为 False。
    """
    from .models import RecordedEventTarget

    # 页面级工具栏按钮 — 遇到则终止扫描
    _PAGE_TOOLBAR_ACTIONS = frozenset(
        {"保存", "提交", "删除", "新增", "增行", "删行", "导出", "导入", "审核", "弃审", "打印"}
    )
    # 弹窗内确认/取消按钮 — 消费但不终止
    _POPUP_BUTTONS = frozenset({"确定", "确认", "OK", "取消", "关闭", "Cancel", "是", "否"})

    result: list[RecordedEvent] = []
    consumed: set[int] = set()

    for i, e in enumerate(events):
        if i in consumed:
            continue

        # ★ 检测：点击可编辑表格单元格
        is_editable_cell_click = (
            e.type == "click"
            and e.target.in_table
            and not e.target.in_table_header
            and (
                e.target.editable_row_number is not None
                or e.target.is_reference_trigger
            )
        )

        # 兜底：in_table click 后续紧跟 dialog_open（参照弹窗打开）
        # ★ 不使用 is_popup_reference，因为它对弹窗内所有元素都为 True
        # ★ 扩大搜索范围到 8 个事件，因为中间可能有重复 click 和 late change 事件
        if not is_editable_cell_click:
            if e.type == "click" and e.target.in_table and not e.target.in_table_header:
                for j in range(i + 1, min(i + 9, len(events))):
                    ej = events[j]
                    if ej.type == "dialog_open":
                        is_editable_cell_click = True
                        break
                    # 同一个 table cell 的重复 click（如点击 cell 内的 icon）→ 跳过继续
                    ej_fid = ej.target.fieldid or ""
                    if (
                        ej.type == "click"
                        and (
                            ej_fid == e.target.fieldid
                            # ★ 子元素点击（如 btn_icon）的 fieldid 以父 fieldid 为前缀
                            or (e.target.fieldid and ej_fid.startswith(e.target.fieldid + "_"))
                            # ★ 父 cell 的 fieldid 可能没有行号后缀，子元素有
                            or (e.target.fieldid and ej_fid.startswith(e.target.fieldid))
                        )
                    ):
                        continue
                    # late change 事件（如表单字段的延迟 change）→ 跳过继续
                    if ej.type in ("input", "change") and not ej.target.in_table:
                        continue
                    if ej.type == "click":
                        break

        if not is_editable_cell_click:
            if i not in consumed:
                result.append(e)
            continue

        # ★ 解析 fieldid 获取 table/column（比 JS 注入更可靠）
        parsed_fid = _parse_editable_fieldid_safe(e.target.fieldid)
        fid_table = parsed_fid[0] if parsed_fid else None
        fid_column = parsed_fid[1] if parsed_fid else None
        fid_row = parsed_fid[2] if parsed_fid else None

        # ★ 如果 anchor 的 fieldid 没有行号（如 plzf_skrxx_table_productNameShow），
        # 尝试从后续的 btn_icon 点击中获取完整的 fieldid
        if not parsed_fid:
            for j in range(i + 1, min(i + 9, len(events))):
                ej = events[j]
                if ej.type == "dialog_open":
                    break
                ej_parsed = _parse_editable_fieldid_safe(ej.target.fieldid)
                if ej_parsed:
                    fid_table = ej_parsed[0]
                    fid_column = ej_parsed[1]
                    fid_row = ej_parsed[2]
                    break

        # 提取列名：★ 优先使用 fieldid 解析结果，不信任 JS 注入的 editable_column
        # JS 注入经常误提取表格第一列表头（如 "序号"、"申请单号"）作为列名
        js_col = e.target.editable_column
        if js_col and (_looks_like_wrong_metadata(js_col, e.target.fieldid) or fid_column):
            # ★ 如果 fieldid 解析出了列名，不信任 JS 注入的 editable_column
            js_col = None
        col = (
            fid_column  # ★ fieldid 解析结果优先
            or e.target.column_header
            or js_col
            or e.target.label_text
            or e.target.placeholder
            or e.target.aria_label
        )
        row_num = e.target.editable_row_number or fid_row or 1
        # ★ 不信任 JS 注入的 editable_table_name 当它明显错误（如 "序号"）
        js_table = e.target.editable_table_name
        if js_table and (_looks_like_wrong_metadata(js_table, e.target.fieldid) or fid_table):
            # ★ 如果 fieldid 解析出了表名，不信任 JS 注入的 editable_table_name
            js_table = None
        table_name = fid_table or js_table
        col_from_popup: str | None = None

        # ★ 范围扫描：从 i+1 开始，直到终止条件
        filter_text: str | None = None
        match_info: dict[str, Any] | None = None
        scan_indices: list[int] = []
        found_match = False
        found_confirm = False
        found_dialog_close = False
        seen_dialog_open = False  # ★ 是否已看到 dialog_open（参照弹窗打开）

        for j in range(i + 1, min(i + 21, len(events))):
            if j in consumed:
                continue
            ej = events[j]
            ej_text = (ej.target.text or "").strip()

            # ★ 在 dialog_open 之前，跳过不相关的表单字段事件（如延迟到达的 change）
            # 这些事件不属于参照弹窗交互，不应被消费也不应终止扫描
            if not seen_dialog_open:
                if ej.type == "dialog_open":
                    seen_dialog_open = True
                    scan_indices.append(j)
                    continue
                # 同一 cell 的重复 click → 消费
                if ej.type == "click" and ej.target.fieldid == e.target.fieldid:
                    scan_indices.append(j)
                    continue
                # 表单字段的延迟 change/input → 跳过（不消费，不终止）
                if ej.type in ("input", "change") and not ej.target.in_table:
                    continue
                # 其他 click → 可能是参照触发器图标等，消费
                if ej.type == "click":
                    scan_indices.append(j)
                    continue
                continue

            # ── 以下终止条件仅在 dialog_open 之后生效 ──

            # ── 终止条件 1: 工具栏按钮（保存/提交等）──
            if (
                ej.type == "click"
                and ej_text in _PAGE_TOOLBAR_ACTIONS
            ):
                break

            # ── 终止条件 2: 下一个可编辑表格单元格（不同列，且不在弹窗内）──
            # ★ 弹窗内的表格行选择（fieldid 含 _0, _1 等后缀）不应终止扫描
            # 只有弹窗关闭后用户点击了另一个主表单元格才应终止
            if (
                ej.type == "click"
                and ej.target.in_table
                and ej.target.fieldid != e.target.fieldid
                and not ej.target.fieldid.startswith(e.target.fieldid + "_")
                and ej_text not in _POPUP_BUTTONS
                and "_modal_ok" not in (ej.target.fieldid or "")
                and found_confirm  # ★ 仅在确定按钮已点击后才终止（弹窗已关闭）
            ):
                break

            # ── 终止条件 3: 表单字段输入（用户开始填别的字段）──
            if (
                ej.type in ("input", "change")
                and not ej.target.in_table
                and "_table_" not in (ej.target.fieldid or "")
            ):
                break

            # ★ 范围内所有事件都消费
            scan_indices.append(j)

            # 收集 dialog_close
            if ej.type == "dialog_close":
                found_dialog_close = True
                # dialog_close 后再扫描 1-2 个事件看有没有"确定"
                # （有些 UI 中"确定"在 dialog_close 之后才触发）
                continue

            # 收集 filter 文本
            if ej.type in ("input", "change") and ej.target.value:
                filter_text = ej.target.value
                if not col and not col_from_popup and ej.target.label_text:
                    col_from_popup = ej.target.label_text

            # 收集 popup_title
            if not col and not col_from_popup and ej.target.popup_title:
                col_from_popup = ej.target.popup_title

            # 处理 click 事件
            if ej.type == "click":
                # 确认按钮
                if ej_text in ("确定", "确认", "OK"):
                    found_confirm = True
                    continue
                # 取消/关闭按钮 — 不影响 match 收集
                if ej_text in ("取消", "关闭", "Cancel"):
                    continue

                # 收集 match 信息（选行 click）
                # ★ 只使用 cell_text（单元格精确值），不用 row_text（整行文本会污染）
                # ★ 也检查 editable_row_number（JS 端提取的行号），作为选行信号
                if ej.target.cell_text or ej.target.editable_row_number is not None:
                    cell_val = ej.target.cell_text
                    # ★ 清理 cell_text：太长的可能是整行文本
                    if cell_val and len(cell_val) > 50:
                        cell_val = ej.target.text if ej.target.text and len(ej.target.text) <= 30 else None
                    # ★ 如果 cell_text 为空或太长，尝试用 text 属性（不超过 30 字符）
                    if not cell_val:
                        cell_val = ej.target.text if ej.target.text and len(ej.target.text) <= 30 else None
                    # ★ 如果仍然没有值，尝试用 value 属性
                    if not cell_val and ej.target.value and len(str(ej.target.value)) <= 30:
                        cell_val = str(ej.target.value)
                    # ★ match column: 优先使用 fieldid 解析的列名，不信任 JS 注入
                    js_match_col = ej.target.editable_column
                    if js_match_col and _looks_like_wrong_metadata(js_match_col, ej.target.fieldid):
                        js_match_col = None
                    ej_parsed = _parse_editable_fieldid_safe(ej.target.fieldid)
                    # ★ fieldid 解析结果优先，其次 column_header，最后用 anchor 的列名
                    match_col = (
                        (ej_parsed[1] if ej_parsed else None)
                        or ej.target.column_header
                        or js_match_col
                        or col  # 用 anchor 的列名作为兜底
                        or "序号"
                    )
                    if cell_val:
                        match_info = {
                            "column": match_col,
                            "equals": cell_val,
                        }
                        found_match = True

            # dialog_open 也标记
            if ej.type == "dialog_open":
                # 弹窗打开了，说明参照交互开始
                pass

        # 判断是否成功：找到了 match 信息就算成功
        # （found_confirm 和 found_dialog_close 是额外信号但不是必需的）
        if found_match:
            # 构建结构化值
            structured: dict[str, Any] = {}
            if filter_text:
                structured["filter"] = filter_text
            structured["match"] = match_info

            # 最终列名
            final_col = col or col_from_popup
            if not final_col or final_col == "参照字段":
                # ★ 用 fid_column（可能来自 scan 事件中的 btn_icon fieldid）
                if fid_column and not fid_column.isdigit():
                    final_col = fid_column
            # ★ 从 fieldid 中提取列名（如 plzf_skrxx_table_productNameShow → productNameShow）
            if not final_col or final_col == "参照字段":
                fid = e.target.fieldid or ""
                table_prefix = table_name or ""
                if table_prefix and fid.startswith(table_prefix + "_"):
                    final_col = fid[len(table_prefix) + 1:]
                elif "_table_" in fid:
                    final_col = fid.split("_table_", 1)[-1]
            if not final_col:
                final_col = "参照字段"

            # 合成 change 事件
            synthetic = RecordedEvent(
                seq=e.seq,
                timestamp=e.timestamp,
                type="change",
                target=RecordedEventTarget(
                    fieldid=e.target.fieldid,
                    label_text=final_col,
                    text=final_col,
                    tag_name="input",
                    in_table=True,
                    in_dialog=False,
                    region_type="main_table",
                    value=filter_text or "",
                    editable_row_number=row_num,
                    editable_column=final_col,
                    editable_table_name=table_name,
                    editable_column_group=e.target.editable_column_group,
                    structured_value=structured,
                ),
                context=e.context,
                meta=e.meta,
            )
            result.append(synthetic)
            consumed.add(i)
            for si in scan_indices:
                consumed.add(si)
            continue

        # 未找到 match → 保留原事件
        if i not in consumed:
            result.append(e)

    return result


# 噪声 label 特征：含图标占位 subicon / 文本过长（导航栏、头像区等整段文本）
_NOISE_LABEL_HINTS = ("subicon", "暂无数据", "小计", "加载中")
_NOISE_LABEL_MAX_LEN = 30


def _is_noise_step(step: dict[str, Any]) -> bool:
    """过滤噪声步骤（toolbar/dialog 的超长文本点击、_drag 拖拽手柄、table-body 空区域等）。"""
    component = step.get("component")
    target = step.get("target") or {}
    label = str(target.get("label") or "")
    fieldid = str(target.get("fieldid") or "")

    # _drag 拖拽手柄 — 总是噪声
    if "_drag" in fieldid:
        return True

    # first_query_drag — 查询区拖拽手柄，噪声
    if fieldid == "first_query_drag":
        return True

    # table-body 容器点击 — 噪声（用户点在了表格空白区域）
    if fieldid == "table-body" or fieldid.endswith("_table-body"):
        return True

    # toolbar 噪声：含 subicon 或文本过长
    if component == "toolbar":
        if any(hint in label for hint in _NOISE_LABEL_HINTS):
            return True
        if len(label) > _NOISE_LABEL_MAX_LEN:
            return True
    # dialog 噪声：文本过长（整个面板内容被误识别为 dialog 按钮）
    if component == "dialog":
        if len(label) > _NOISE_LABEL_MAX_LEN:
            return True
    # table 噪声：空标签（空单元格点击，没有有效文本）
    if component == "table" and not label:
        return True
    # tree 噪声：空标签（switcher 点击被误识别为 tree.select）
    if component == "tree" and not label:
        return True
    return False


def _filter_redundant_tree_popup(
    steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """去除已被 form.fill 覆盖的冗余 tree.select / popup_reference.select 步骤。

    当 _preprocess_form_interactions 成功将下拉/日期选择合成为 form.fill 字段时，
    原始的 tree/popup_reference 事件应已被消费。但某些边缘情况下它们可能泄漏，
    此函数作为安全网：如果 tree.select 的 label 或 popup_reference 的 match.equals
    已出现在某个 form.fill 的字段值中，则移除该冗余步骤。
    """
    if not steps:
        return steps

    # 收集所有 form.fill 中的字段值
    form_values: set[str] = set()
    for s in steps:
        if s.get("component") == "form" and s.get("operation") == "fill":
            fields = (s.get("target") or {}).get("fields") or {}
            for v in fields.values():
                if isinstance(v, str) and v:
                    form_values.add(v.strip())

    if not form_values:
        return steps

    result: list[dict[str, Any]] = []
    for s in steps:
        comp = s.get("component")
        if comp == "tree" and s.get("operation") == "select":
            label = str((s.get("target") or {}).get("label") or "").strip()
            if label and label in form_values:
                continue  # 冗余，跳过
        if comp == "popup_reference" and s.get("operation") == "select":
            match = (s.get("target") or {}).get("match") or {}
            equals = str(match.get("equals") or "").strip()
            if equals and equals in form_values:
                continue  # 冗余，跳过
        result.append(s)
    return result


def _merge_form_fills(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """合并同一弹窗上下文中的多个 form.fill 步骤为一个。

    用户在表单中填写字段时，可能穿插 tree.select（参照选择）、tab.click
    等操作，导致 form.fill 被拆成多个步骤。此函数将同一弹窗内的所有
    form.fill 合并为一个，字段取并集（后填的覆盖先填的同名字段）。

    合并后的步骤放在第一个 form.fill 出现的位置。
    """
    if not steps:
        return steps

    # 收集所有 form.fill 步骤的索引
    form_indices = [
        i for i, s in enumerate(steps)
        if s.get("component") == "form" and s.get("operation") == "fill"
    ]
    if len(form_indices) <= 1:
        return steps

    # 合并所有 form.fill 的 fields
    merged_fields: dict[str, str] = {}
    for i in form_indices:
        fields = (steps[i].get("target") or {}).get("fields") or {}
        merged_fields.update(fields)

    # 构建合并后的 form.fill 步骤（放在第一个 form.fill 的位置）
    merged_step: dict[str, Any] = {
        "component": "form",
        "operation": "fill",
        "target": {"fields": merged_fields},
    }

    # 重建步骤列表：用合并后的步骤替换所有 form.fill，其他步骤保持原序
    result: list[dict[str, Any]] = []
    first_form = True
    for i, s in enumerate(steps):
        if i in form_indices:
            if first_form:
                result.append(merged_step)
                first_form = False
            # 跳过后续的 form.fill 步骤（已合并）
        else:
            result.append(s)
    return result


def _dedup_editable_table_fills(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """去除重复的 editable_table.fill_row 步骤。

    用户在可编辑表格中填写一行后点「保存」，保存后表格可能刷新导致
    同一行需要重新填写。如果两次 fill_row 的表名、行号、字段完全相同，
    则丢弃第二次（它是保存后表格刷新的重复录入）。

    如果字段有差异（用户补充了新字段），则合并字段后保留一次。
    """
    if not steps:
        return steps

    result: list[dict[str, Any]] = []
    for step in steps:
        if step.get("component") != "editable_table" or step.get("operation") != "fill_row":
            result.append(step)
            continue

        target = step.get("target") or {}
        table = target.get("table") or ""
        row = target.get("row_number")
        fields = target.get("fields") or {}

        # 检查 result 中是否已有同表同行的 fill_row
        merged = False
        for prev in result:
            if prev.get("component") != "editable_table" or prev.get("operation") != "fill_row":
                continue
            prev_target = prev.get("target") or {}
            prev_table = prev_target.get("table") or ""
            prev_row = prev_target.get("row_number")
            prev_fields = prev_target.get("fields") or {}

            if prev_table == table and prev_row == row:
                # 同表同行：合并字段（后值覆盖前值）
                prev_fields.update(fields)
                prev_target["fields"] = prev_fields
                merged = True
                break

        if not merged:
            result.append(step)

    return result


def extract_menu_path(events: list[RecordedEvent]) -> str | None:
    """从导航事件提取菜单路径。

    当前从 URL 提取 serviceCode 作为占位（阶段二将改为反查中文菜单路径）。
    """
    for event in events:
        if event.type == "navigation" and event.target.value:
            url = event.target.value
            match = re.search(r"/service/([^/?#]+)", url)
            if match:
                return match.group(1)
            match = re.search(r"#/service/([^/?#]+)", url)
            if match:
                return match.group(1)
    return None


def build_dsl_document(
    session: RecordingSession,
    abstract: bool = False,
    auto_capture: bool = False,
) -> DslDocument:
    """从录制会话构建完整的 DSL 文档（suite + cases）。"""
    steps = convert_events_to_steps(session.events, abstract=abstract, auto_capture=auto_capture)

    menu_path = session.menu_path or extract_menu_path(session.events)

    case_steps: list[dict[str, Any]] = []
    if menu_path:
        case_steps.append({"action": "open_menu", "menu_path": menu_path})
    case_steps.extend(steps)
    case_steps = _deduplicate_steps(case_steps)

    suite_code = session.suite_code or "recorded_suite"
    suite_name = session.suite_name or "录制测试集"

    suite = DslTestSuite(
        code=suite_code,
        name=suite_name,
        tenant=session.tenant,
        default_org=session.default_org,
        fiscal_year=session.fiscal_year,
    )

    case = DslTestCase(
        code=f"{suite_code}_case_1",
        name=f"{suite_name} - 用例1",
        user=session.user,
        default_org=session.default_org,
        steps=case_steps,
    )

    return DslDocument(suite=suite, cases=[case])


def _merge_toolbar_sub_labels(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """合并 toolbar 下拉子选项：主按钮 + 子选项 → 带 sub_label 的单步。

    模式：连续两个 toolbar.click，第一个 label 是已知动作（如「新增」），
    第二个 label 不是已知动作且不是行操作文本 → 合并为
    ``{label: 第一个, sub_label: 第二个}``。

    与 ydf-browser 示例对齐：
        label: 新增
        sub_label: 特定目标类
    """
    from .registry import _KNOWN_ACTION_LABELS, _TABLE_ROW_ACTION_TEXTS

    if len(steps) < 2:
        return steps
    result: list[dict[str, Any]] = []
    i = 0
    while i < len(steps):
        cur = steps[i]
        nxt = steps[i + 1] if i + 1 < len(steps) else None
        if (
            nxt is not None
            and cur.get("component") == "toolbar"
            and cur.get("operation") == "click"
            and nxt.get("component") == "toolbar"
            and nxt.get("operation") == "click"
        ):
            cur_label = str((cur.get("target") or {}).get("label") or "")
            nxt_label = str((nxt.get("target") or {}).get("label") or "")
            # 第一个是已知动作（新增/删除/导入等），第二个不是已知动作也不是行操作
            if (
                cur_label in _KNOWN_ACTION_LABELS
                and cur_label not in ("确定", "确认", "取消", "关闭", "返回")
                and nxt_label
                and nxt_label not in _KNOWN_ACTION_LABELS
                and nxt_label not in _TABLE_ROW_ACTION_TEXTS
                and len(nxt_label) < 20  # 子选项通常很短
            ):
                merged = dict(cur)
                merged["target"] = dict(cur.get("target") or {})
                merged["target"]["sub_label"] = nxt_label
                result.append(merged)
                i += 2
                continue
        result.append(cur)
        i += 1
    return result


def _deduplicate_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """去除连续的完全相同的步骤。"""
    if not steps:
        return steps
    result = [steps[0]]
    for step in steps[1:]:
        if step != result[-1]:
            result.append(step)
    return result


# ── capture 自动注入 ────────────────────────────────────────

def _sanitize_variable_name(label: str) -> str:
    """将字段标签转为合法的 capture 变量名。

    保留中文字符/字母/数字，清理多余空白，限制长度 30。
    """
    name = re.sub(r'\s+', '', label)
    if len(name) > 30:
        name = name[:30]
    return name if name else "field"


def _inject_form_captures(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """在 ``form.fill`` 步骤后自动注入 ``form.capture_values``。

    捕获刚刚填写的字段值，供后续 case 引用。
    """
    result: list[dict[str, Any]] = []
    for step in steps:
        result.append(step)
        if step.get("component") == "form" and step.get("operation") == "fill":
            target = step.get("target") or {}
            fields = target.get("fields") or target.get("values") or {}
            if not fields:
                field_label = target.get("field")
                if field_label:
                    fields = {field_label: target.get("equals", "")}
            if fields:
                capture: dict[str, str] = {}
                for field_label in fields:
                    var_name = _sanitize_variable_name(str(field_label))
                    capture[var_name] = str(field_label)
                if capture:
                    result.append({
                        "component": "form",
                        "operation": "capture_values",
                        "target": {"capture": capture},
                    })
    return result


def _inject_table_captures(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """在 ``table_row_selection.select`` 步骤后自动注入 ``table.capture_row_values``。

    捕获选中行的关键列值，供后续 case 引用。
    """
    result: list[dict[str, Any]] = []
    for step in steps:
        result.append(step)
        if step.get("component") == "table_row_selection" and step.get("operation") == "select":
            target = step.get("target") or {}
            match = target.get("match")
            if match and isinstance(match, dict):
                column = match.get("column")
                equals = match.get("equals")
                if column and equals:
                    var_name = _sanitize_variable_name(str(column))
                    result.append({
                        "component": "table",
                        "operation": "capture_row_values",
                        "target": {
                            "table": target.get("table", ""),
                            "table_name": target.get("table_name", ""),
                            "match": {"column": str(column), "equals": str(equals)},
                            "capture": {var_name: str(column)},
                        },
                    })
    return result


def _inject_captures(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """对生成的步骤列表注入 capture 步骤。

    目前支持：
    - ``form.fill`` → ``form.capture_values``（捕获填写的字段值）
    - ``table_row_selection.select`` → ``table.capture_row_values``（捕获选中行的列值）
    """
    steps = _inject_form_captures(steps)
    steps = _inject_table_captures(steps)
    return steps


def inject_captures(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """公开 API：对生成的步骤列表注入 capture 步骤。见 _inject_captures。"""
    return _inject_captures(steps)


class _RoundTripDumper(yaml.Dumper):
    """保证字符串 round-trip 安全的 Dumper。

    对会被 YAML 解析器误解为数字/布尔/null 的字符串值强制加引号，避免
    ``default_org: 049002`` 被加载为 int 49002（丢失前导零）。
    """


def _looks_like_non_str_scalar(value: str) -> bool:
    """值是否会被 YAML safe_load 解析为非字符串类型。"""
    if not value:
        return False
    try:
        return not isinstance(yaml.safe_load(value), str)
    except Exception:
        return False


def _represent_str(dumper: yaml.Dumper, data: str) -> Any:
    style = "'" if _looks_like_non_str_scalar(data) else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_RoundTripDumper.add_representer(str, _represent_str)


def dsl_to_yaml(document: DslDocument) -> str:
    """将 DslDocument 序列化为 YAML 字符串。"""
    suite_dict = document.suite.to_dict()
    cases_list = [case.to_dict() for case in document.cases]

    # 清理空字段
    for case in cases_list:
        for key in ("description", "user", "default_org"):
            if key in case and not case[key]:
                del case[key]
        if "tags" in case and not case["tags"]:
            del case["tags"]

    for key in ("description", "default_org", "fiscal_year"):
        if key in suite_dict and not suite_dict[key]:
            del suite_dict[key]
    if "runtime_variables" in suite_dict and not suite_dict["runtime_variables"]:
        del suite_dict["runtime_variables"]

    output = {"suite": suite_dict, "cases": cases_list}
    return yaml.dump(
        output,
        Dumper=_RoundTripDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
    )


def load_events_from_jsonl(path: str) -> list[RecordedEvent]:
    """从 JSONL 文件加载录制事件。"""
    events: list[RecordedEvent] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            events.append(RecordedEvent.from_dict(json.loads(line)))
    return events


def load_events_from_json(path: str) -> list[RecordedEvent]:
    """从 JSON 文件（数组或含 events 键的对象）加载录制事件。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [RecordedEvent.from_dict(e) for e in data]
    if isinstance(data, dict):
        event_list = data.get("events", data.get("data", [data]))
        if isinstance(event_list, list):
            return [RecordedEvent.from_dict(e) for e in event_list]
    raise ValueError(f"无法从文件 {path} 解析录制事件")
