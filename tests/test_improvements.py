"""P0/P1 改进项回归测试。

覆盖本次录制器完善的五块能力：
  - P1-4 断言录制（checkpoint 分流 + notification.assert 自动前置）
  - P1-5 上传文件名捕获（file change 事件回填到 upload 占位符）
  - P1-6 富文本（contenteditable）form.fill
  - P1-7 workflow_result 结果层识别（confirm/details/assert）
  - 基础识别回归（file 输入不再误入 form.fill 等）
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ydf_recorder.models import (  # noqa: E402
    RecordedEvent,
    RecordedEventContext,
    RecordedEventTarget,
)
from ydf_recorder.converter import (  # noqa: E402
    _backfill_upload_filenames,
    _inject_notification_asserts,
    _is_date_cell,
    _preprocess_form_interactions,
)
from ydf_recorder.registry import (  # noqa: E402
    build_target,
    classify_event,
    is_form_input,
)


def ev(etype: str, seq: int = 1, timestamp: int = 100, context=None, **target_kwargs) -> RecordedEvent:
    """构造测试事件（context 可选，默认通用上下文）。"""
    return RecordedEvent(
        type=etype,
        seq=seq,
        timestamp=timestamp,
        target=RecordedEventTarget(**target_kwargs),
        context=context or RecordedEventContext(url="http://test", title="测试"),
    )


WF_TEXT = "提交请求已执行完毕 总数 3 成功 2 条 失败 1 条"
WF = dict(is_workflow_result=True, workflow_result_text=WF_TEXT)


class TestP15UploadFilename(unittest.TestCase):
    """P1-5：文件名回填与占位符生成。"""

    def test_backfill_import_upload(self):
        events = [
            ev("click", seq=1, text="导入", is_upload_trigger=True),
            ev("change", seq=3, input_type="file", tag_name="input", value="预算表.xlsx"),
        ]
        events = _backfill_upload_filenames(events)
        self.assertEqual(events[0].target.uploaded_file_name, "预算表.xlsx")
        target = build_target("import", "upload", [events[0]])
        self.assertEqual(target["file"], "<请填写文件路径: 预算表.xlsx>")

    def test_backfill_attachment_multi_file(self):
        events = [
            ev("click", seq=1, text="上传附件", is_upload_trigger=True),
            ev("change", seq=2, input_type="file", tag_name="input", value="a.pdf, b.pdf"),
        ]
        events = _backfill_upload_filenames(events)
        target = build_target("attachment", "upload", [events[0]])
        self.assertEqual(target["attachments"][0]["file"], "<请填写文件路径: a.pdf, b.pdf>")

    def test_cancelled_upload_keeps_placeholder(self):
        events = [ev("click", seq=1, text="导入", is_upload_trigger=True)]
        events = _backfill_upload_filenames(events)
        target = build_target("import", "upload", [events[0]])
        self.assertEqual(target["file"], "<请填写文件路径>")

    def test_file_change_not_classified_as_form_fill(self):
        event = ev("change", input_type="file", tag_name="input", value="x.pdf")
        self.assertNotEqual(classify_event(event), ("form", "fill"))

    def test_file_change_not_classified_as_fill_row(self):
        event = ev(
            "change", input_type="file", tag_name="input", value="x.pdf", in_table=True,
        )
        self.assertNotEqual(classify_event(event), ("editable_table", "fill_row"))


class TestP16Richtext(unittest.TestCase):
    """P1-6：富文本 contenteditable 输入归 form.fill。"""

    def test_richtext_input_is_form_input(self):
        event = ev("input", tag_name="div", widget_type="richtext", value="事由说明")
        self.assertTrue(is_form_input(event))
        self.assertEqual(classify_event(event), ("form", "fill"))

    def test_richtext_build_target(self):
        event = ev(
            "input", tag_name="div", widget_type="richtext",
            label_text="事由", value="出差报销事由说明",
        )
        target = build_target("form", "fill", [event])
        self.assertEqual(target["fields"].get("事由"), "出差报销事由说明")

    def test_plain_div_input_ignored(self):
        event = ev("input", tag_name="div", value="x")
        self.assertFalse(is_form_input(event))
        self.assertIsNone(classify_event(event))


class TestP17WorkflowResult(unittest.TestCase):
    """P1-7：工作流批量结果层识别。"""

    def test_confirm_click(self):
        event = ev("click", text="确认", tag_name="button", in_dialog=True, **WF)
        pair = classify_event(event)
        self.assertEqual(pair, ("workflow_result", "confirm"))
        self.assertEqual(build_target(*pair, [event]), {"label": "确认"})

    def test_details_click(self):
        event = ev("click", text="查看详情", tag_name="span", **WF)
        pair = classify_event(event)
        self.assertEqual(pair, ("workflow_result", "details"))
        self.assertEqual(build_target(*pair, [event]), {"label": "查看详情"})

    def test_checkpoint_assert_with_counts(self):
        event = ev("checkpoint", **WF)
        pair = classify_event(event)
        self.assertEqual(pair, ("workflow_result", "assert"))
        target = build_target(*pair, [event])
        self.assertEqual(target, {"total": 3, "succeeded": 2, "failed": 1})

    def test_normal_dialog_confirm_unaffected(self):
        event = ev("click", text="确认", tag_name="button", in_dialog=True)
        self.assertNotEqual(classify_event(event), ("workflow_result", "confirm"))

    def test_input_inside_result_layer_still_fills(self):
        event = ev(
            "input", tag_name="input", value="abc",
            region_type="content_card", **WF,
        )
        self.assertEqual(classify_event(event), ("form", "fill"))


class TestP14CheckpointAsserts(unittest.TestCase):
    """P1-4：Alt+点击检查点分流与 notification.assert 自动前置。"""

    def test_notification_assert_from_checkpoint(self):
        event = ev(
            "checkpoint", is_notification_close=True,
            notification_text="操作成功",
        )
        pair = classify_event(event)
        self.assertEqual(pair, ("notification", "assert"))
        target = build_target(*pair, [event])
        self.assertEqual(target.get("contains"), "操作成功")

    def test_table_assert_from_checkpoint(self):
        event = ev(
            "checkpoint", in_table=True,
            row_data=[{"column": "单据编码", "value": "P20260101"}],
        )
        pair = classify_event(event)
        self.assertEqual(pair, ("table", "assert_row_values"))

    def test_form_assert_fallback(self):
        event = ev("checkpoint", label_text="备注", value="测试备注")
        pair = classify_event(event)
        self.assertEqual(pair, ("form", "assert_values"))
        target = build_target(*pair, [event])
        self.assertEqual(target["fields"].get("备注"), "测试备注")

    def test_inject_notification_asserts(self):
        steps = [
            {"component": "toolbar", "operation": "click", "target": {"label": "提交"}},
            {"component": "notification", "operation": "close",
             "target": {"contains": "提交成功"}},
            {"component": "form", "operation": "fill", "target": {"fields": {"a": "1"}}},
        ]
        result = _inject_notification_asserts(steps)
        self.assertEqual(len(result), 4)
        self.assertEqual(
            result[1],
            {"component": "notification", "operation": "assert",
             "target": {"contains": "提交成功"}},
        )
        self.assertEqual(result[2]["operation"], "close")


class TestDateCell(unittest.TestCase):
    """P0-2：date_cell 识别（widget_type 与日期前缀双通道）。"""

    def test_widget_type_channel(self):
        event = ev("click", widget_type="date_cell", cell_text="2026-09-02")
        self.assertTrue(_is_date_cell(event))

    def test_regex_channel(self):
        event = ev("click", cell_text="2026-01-31 12:00")
        self.assertTrue(_is_date_cell(event))

    def test_non_date(self):
        event = ev("click", cell_text="江西省局本级")
        self.assertFalse(_is_date_cell(event))


class TestRegressionBasics(unittest.TestCase):
    """基础识别回归：防止新逻辑破坏既有行为。"""

    def test_normal_form_input(self):
        event = ev("input", tag_name="input", region_type="content_card", value="hi")
        self.assertEqual(classify_event(event), ("form", "fill"))

    def test_upload_click_without_file(self):
        event = ev("click", text="上传附件", is_upload_trigger=True)
        self.assertEqual(classify_event(event), ("attachment", "upload"))

    def test_navigation_events_ignored(self):
        self.assertIsNone(classify_event(ev("navigation")))
        self.assertIsNone(classify_event(ev("hover")))


if __name__ == "__main__":
    unittest.main()


# ════════════════════════════════════════════════════════════════
# 表单合并修复（问题1：碎片化 / 问题2：切换被覆盖）
# ════════════════════════════════════════════════════════════════

from ydf_recorder.converter import (  # noqa: E402
    _merge_form_fills,
    _form_ctx_of,
    convert_events_to_steps,
)
from ydf_recorder.registry import can_coalesce  # noqa: E402

CTX_MAIN = (False, "", "基本信息", "http://x/bill", "单据")
CTX_TAB2 = (False, "", "明细信息", "http://x/bill", "单据")


def fill_step(fields, ctx=CTX_MAIN):
    return {
        "component": "form", "operation": "fill",
        "target": {"fields": fields}, "_form_ctx": ctx,
    }


def step(component, operation, label=None):
    s = {"component": component, "operation": operation}
    if label is not None:
        s["target"] = {"label": label}
    return s


class TestFormMergeIssue1(unittest.TestCase):
    """问题1：一个表单的操作应合并为一个 form.fill（非相邻片段）。"""

    def test_interleaved_popup_does_not_fragment(self):
        steps = [
            fill_step({"摘要": "v1"}),
            step("popup_reference", "select"),
            fill_step({"备注": "v2"}),
            step("tree", "select"),
            fill_step({"金额": "100"}),
        ]
        result = _merge_form_fills(steps)
        fills = [s for s in result if s["component"] == "form"]
        self.assertEqual(len(fills), 1)
        self.assertEqual(
            fills[0]["target"]["fields"],
            {"摘要": "v1", "备注": "v2", "金额": "100"},
        )
        # 穿插步骤保留在合并步骤之后（原相对顺序）
        self.assertEqual(result[0]["component"], "form")
        self.assertEqual(result[1], step("popup_reference", "select"))
        self.assertEqual(result[2], step("tree", "select"))

    def test_later_value_overrides_same_field(self):
        steps = [
            fill_step({"摘要": "旧值"}),
            step("popup_reference", "select"),
            fill_step({"摘要": "新值"}),
        ]
        result = _merge_form_fills(steps)
        fills = [s for s in result if s["component"] == "form"]
        self.assertEqual(fills[0]["target"]["fields"], {"摘要": "新值"})

    def test_internal_key_stripped(self):
        result = _merge_form_fills([fill_step({"a": "1"})])
        self.assertNotIn("_form_ctx", result[0])

    def test_adjacent_merge_regression(self):
        steps = [fill_step({"a": "1"}), fill_step({"b": "2"})]
        result = _merge_form_fills(steps)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["target"]["fields"], {"a": "1", "b": "2"})

    def test_missing_ctx_adjacent_merge_regression(self):
        steps = [
            {"component": "form", "operation": "fill", "target": {"fields": {"a": "1"}}},
            {"component": "form", "operation": "fill", "target": {"fields": {"b": "2"}}},
        ]
        result = _merge_form_fills(steps)
        self.assertEqual(len(result), 1)

    def test_save_button_ends_session(self):
        steps = [
            fill_step({"a": "1"}),
            step("toolbar", "click", "保存"),
            fill_step({"b": "2"}),
        ]
        result = _merge_form_fills(steps)
        fills = [s for s in result if s["component"] == "form"]
        self.assertEqual(len(fills), 2)

    def test_assert_is_barrier(self):
        steps = [
            fill_step({"a": "1"}),
            {"component": "form", "operation": "assert_values",
             "target": {"fields": {"a": "1"}}},
            fill_step({"b": "2"}),
        ]
        result = _merge_form_fills(steps)
        fills = [s for s in result if s["component"] == "form" and s["operation"] == "fill"]
        self.assertEqual(len(fills), 2)


class TestFormSwitchIssue2(unittest.TestCase):
    """问题2：表单切换必须保留且不得跨切换合并。"""

    def test_tab_switch_preserved_and_not_merged(self):
        steps = [
            fill_step({"字段A": "1"}, ctx=CTX_MAIN),
            step("tab", "click", "明细信息"),
            fill_step({"字段B": "2"}, ctx=CTX_TAB2),
        ]
        result = _merge_form_fills(steps)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["target"]["fields"], {"字段A": "1"})
        self.assertEqual(result[1]["component"], "tab")
        self.assertEqual(result[2]["target"]["fields"], {"字段B": "2"})

    def test_switch_back_keeps_separate(self):
        steps = [
            fill_step({"a": "1"}, ctx=CTX_MAIN),
            step("tab", "click", "明细信息"),
            fill_step({"b": "2"}, ctx=CTX_TAB2),
            step("tab", "click", "基本信息"),
            fill_step({"c": "3"}, ctx=CTX_MAIN),
        ]
        result = _merge_form_fills(steps)
        fills = [s for s in result if s["component"] == "form"]
        self.assertEqual(len(fills), 3)

    def test_row_selection_is_barrier(self):
        steps = [
            fill_step({"明细": "第一行"}),
            step("table_row_selection", "select"),
            fill_step({"明细": "第二行"}),
        ]
        result = _merge_form_fills(steps)
        fills = [s for s in result if s["component"] == "form"]
        self.assertEqual(len(fills), 2)

    def test_can_coalesce_blocks_cross_tab(self):
        """切换动作未被识别成步骤时（classify=None 被丢弃），
        can_coalesce 护栏阻止两侧 fill 合并 —— 问题2的兜底。"""
        a = ev("input", tag_name="input", region_type="content_card", value="1",
               context=RecordedEventContext(url="http://x", title="单据", active_tab="基本信息"))
        b = ev("input", tag_name="input", region_type="content_card", value="2",
               context=RecordedEventContext(url="http://x", title="单据", active_tab="明细信息"))
        self.assertFalse(can_coalesce(("form", "fill"), ("form", "fill"), a, b))

    def test_can_coalesce_blocks_cross_dialog_title(self):
        a = ev("input", tag_name="input", region_type="content_card", value="1")
        b = ev("input", tag_name="input", region_type="content_card", value="2",
               context=RecordedEventContext(url="http://x", title="单据", dialog_title="第二步"))
        self.assertFalse(can_coalesce(("form", "fill"), ("form", "fill"), a, b))

    def test_can_coalesce_same_tab_regression(self):
        a = ev("input", tag_name="input", region_type="content_card", value="1")
        b = ev("input", tag_name="input", region_type="content_card", value="2")
        self.assertTrue(can_coalesce(("form", "fill"), ("form", "fill"), a, b))


class TestFormMergeE2E(unittest.TestCase):
    """端到端：穿插通知点击的碎片 fill 合并为一个 form.fill。"""

    def test_e2e_interleaved_notification(self):
        ctx = RecordedEventContext(url="http://x", title="单据", active_tab="基本信息")
        events = [
            ev("input", seq=1, tag_name="input", region_type="content_card",
               fieldid="a", label_text="摘要", value="出差报销", context=ctx),
            ev("click", seq=2, is_notification_close=True,
               notification_text="已保存", text="×", context=ctx),
            ev("input", seq=3, tag_name="input", region_type="content_card",
               fieldid="b", label_text="备注", value="加急", context=ctx),
        ]
        steps = convert_events_to_steps(events)
        fills = [s for s in steps if s["component"] == "form" and s["operation"] == "fill"]
        self.assertEqual(len(fills), 1)
        self.assertEqual(
            fills[0]["target"]["fields"],
            {"摘要": "出差报销", "备注": "加急"},
        )
        # 通知断言/关闭仍在，且 _form_ctx 未泄漏
        for s in steps:
            self.assertNotIn("_form_ctx", s)

    def test_e2e_tab_switch_two_forms(self):
        ctx1 = RecordedEventContext(url="http://x", title="单据", active_tab="基本信息")
        ctx2 = RecordedEventContext(url="http://x", title="单据", active_tab="明细信息")
        events = [
            ev("input", seq=1, tag_name="input", region_type="content_card",
               label_text="摘要", value="v1", context=ctx1),
            ev("click", seq=2, tag_name="div", region_type="tab_bar",
               fieldid="ymbtl_tab", text="明细信息", context=ctx2),
            ev("input", seq=3, tag_name="input", region_type="content_card",
               label_text="备注", value="v2", context=ctx2),
        ]
        steps = convert_events_to_steps(events)
        fills = [s for s in steps if s["component"] == "form" and s["operation"] == "fill"]
        tabs = [s for s in steps if s["component"] == "tab"]
        self.assertEqual(len(fills), 2)
        self.assertEqual(len(tabs), 1)
        self.assertEqual(fills[0]["target"]["fields"], {"摘要": "v1"})
        self.assertEqual(fills[1]["target"]["fields"], {"备注": "v2"})


# ════════════════════════════════════════════════════════════════
# 问题3修复：可编辑表格参照锚点误判吞掉后续 toolbar/弹窗流程
# ════════════════════════════════════════════════════════════════

from ydf_recorder.converter import _parse_editable_fieldid_safe  # noqa: E402


def _ctx(url="http://x", tab="", dlg=""):
    return RecordedEventContext(url=url, title="单据", active_tab=tab, dialog_title=dlg)


class TestEditableRefAnchorIssue3(unittest.TestCase):
    """问题3：复选框/弹窗内点击误判为参照锚点，范围消费吞掉后续 toolbar。"""

    def _suite4_like_events(self):
        """模拟 suite4 真实录制：选行 → toolbar → 弹窗流程 → toolbar。"""
        return [
            ev("click", seq=1, tag_name="input", in_table=True,
               editable_row_number=1, fieldid="first_table_checkbox",
               context=_ctx()),
            ev("change", seq=3, tag_name="input", in_table=True,
               input_type="checkbox", fieldid="first_table_checkbox",
               context=_ctx()),
            ev("click", seq=5, tag_name="span", region_type="top_action_bar",
               text="补充付款人", fieldid="bcfkr_btn", context=_ctx()),
            ev("dialog_open", seq=6, context=_ctx()),
            ev("click", seq=11, tag_name="i", in_table=True,
               is_reference_trigger=True,
               fieldid="fkrxx_form_payAcctName_btn_icon", context=_ctx()),
            ev("click", seq=17, tag_name="span", text="确定",
               fieldid="fkrxx_form_payAcctName_modal", context=_ctx()),
            ev("click", seq=25, tag_name="span", region_type="top_action_bar",
               text="生成凭证", fieldid="create_btn", context=_ctx()),
        ]

    def test_both_toolbars_survive(self):
        steps = convert_events_to_steps(self._suite4_like_events())
        labels = [
            str((s.get("target") or {}).get("label"))
            for s in steps if s["component"] == "toolbar"
        ]
        self.assertIn("补充付款人", labels)
        self.assertIn("生成凭证", labels)

    def test_no_bogus_fill_row_from_checkbox(self):
        steps = convert_events_to_steps(self._suite4_like_events())
        self.assertNotIn(
            "editable_table",
            [s["component"] for s in steps],
        )

    def test_fallback_anchor_requires_table_fid(self):
        """弹窗内参照图标（fid 无 _table_/不可解析）不得成为锚点。"""
        events = [
            ev("click", seq=1, tag_name="i", in_table=True,
               is_reference_trigger=True,
               fieldid="fkrxx_form_payAcctName_btn_icon", context=_ctx()),
            ev("dialog_open", seq=2, context=_ctx()),
            ev("click", seq=3, tag_name="span", region_type="top_action_bar",
               text="生成凭证", fieldid="create_btn", context=_ctx()),
        ]
        steps = convert_events_to_steps(events)
        self.assertNotIn(
            "editable_table",
            [s["component"] for s in steps],
        )
        self.assertIn(
            "生成凭证",
            [str((s.get("target") or {}).get("label")) for s in steps],
        )

    def test_real_editable_refer_still_synthesizes(self):
        """回归：真实可编辑表格参照（fid 可解析）仍正常合成 fill_row。"""
        events = [
            ev("click", seq=1, tag_name="input", in_table=True,
               editable_row_number=1,
               fieldid="plzf_skrxx_table_productNameShow_0", context=_ctx()),
            ev("dialog_open", seq=2, context=_ctx()),
            ev("click", seq=3, tag_name="tr", in_table=True,
               cell_text="商品A", editable_row_number=1,
               fieldid="popup_row_1", context=_ctx()),
            ev("click", seq=4, tag_name="span", text="确定",
               in_dialog=True, context=_ctx()),
            ev("dialog_close", seq=5, context=_ctx()),
        ]
        steps = convert_events_to_steps(events)
        fill_rows = [s for s in steps if s["component"] == "editable_table"
                     and s["operation"] == "fill_row"]
        self.assertEqual(len(fill_rows), 1)
        fields = (fill_rows[0].get("target") or {}).get("fields") or {}
        match_infos = [v for v in fields.values() if isinstance(v, dict) and "match" in v]
        self.assertTrue(match_infos)
        self.assertEqual(match_infos[0]["match"]["equals"], "商品A")

    def test_page_toolbar_region_terminates_scan(self):
        """扫描窗口内出现页面级工具栏点击 → 立即终止，不吞。"""
        events = [
            ev("click", seq=1, tag_name="input", in_table=True,
               editable_row_number=1,
               fieldid="plzf_skrxx_table_productNameShow_0", context=_ctx()),
            # 窗口内（无 dialog_open）直接点页面工具栏
            ev("click", seq=2, tag_name="span", region_type="top_action_bar",
               text="生成凭证", fieldid="create_btn", context=_ctx()),
        ]
        steps = convert_events_to_steps(events)
        labels = [
            str((s.get("target") or {}).get("label"))
            for s in steps if s["component"] == "toolbar"
        ]
        self.assertIn("生成凭证", labels)

    def test_dialog_confirm_label_not_toolbar(self):
        """确定/取消等弹窗词汇不再被误判为 toolbar.click。"""
        e = ev("click", tag_name="span", text="确定", region_type="dialog_page",
               fieldid="fkrxx_form_payAcctName_modal")
        pair = classify_event(e)
        self.assertNotEqual(pair, ("toolbar", "click"))

    def test_parse_editable_fieldid_guard(self):
        self.assertIsNotNone(
            _parse_editable_fieldid_safe("plzf_skrxx_table_productNameShow_0"))
        self.assertIsNone(_parse_editable_fieldid_safe("fkrxx_form_payAcctName"))
        self.assertIsNone(_parse_editable_fieldid_safe("first_table_checkbox"))


# ════════════════════════════════════════════════════════════════
# 问题4修复：弹窗内树选择步骤丢失
# ════════════════════════════════════════════════════════════════

class TestDialogTreeSelectionIssue4(unittest.TestCase):
    """问题4：弹窗内通过树选择数据后，中间步骤未录制。"""

    def _dialog_tree_events(self):
        """模拟：切换开关 → 点参照字段 → 树弹窗 → 选节点 → 确定。"""
        return [
            ev("click", seq=1, tag_name="button", is_switch=True,
               label_text="是否金库退付", fieldid="fkrxx_form_isRefundFromTreas",
               in_dialog=True, context=_ctx(dlg="补充付款人")),
            ev("click", seq=2, tag_name="input", label_text="收款单位",
               fieldid="fkrxx_form_payUnit", in_dialog=True,
               context=_ctx(dlg="补充付款人")),
            ev("dialog_open", seq=3, context=_ctx(dlg="补充付款人")),
            ev("click", seq=4, tag_name="span", region_type="tree",
               text="某市财政局", fieldid="tree_node_1", in_dialog=True,
               context=_ctx(dlg="补充付款人")),
            ev("click", seq=5, tag_name="span", text="确定", in_dialog=True,
               context=_ctx(dlg="补充付款人")),
        ]

    def test_tree_selection_lands_in_form_fill(self):
        steps = convert_events_to_steps(self._dialog_tree_events())
        fills = [s for s in steps if s["component"] == "form"
                 and s["operation"] == "fill"]
        self.assertEqual(len(fills), 1)
        fields = fills[0]["target"]["fields"]
        self.assertEqual(fields.get("是否金库退付"), "true")
        self.assertEqual(fields.get("收款单位"), "某市财政局")

    def test_dialog_confirm_survives(self):
        """回归：空 label 相等误判不再吞掉后续「确定」按钮。"""
        steps = convert_events_to_steps(self._dialog_tree_events())
        confirms = [s for s in steps if s["component"] == "dialog"
                    and s["operation"] == "confirm"]
        self.assertEqual(len(confirms), 1)
        self.assertEqual(confirms[0]["target"]["label"], "确定")

    def test_duplicate_tree_click_still_consumed(self):
        """回归：Pattern 1 消费重复树点击的原有能力不受影响。"""
        events = [
            ev("click", seq=2, tag_name="input", label_text="收款单位",
               fieldid="fkrxx_form_payUnit", in_dialog=True, context=_ctx()),
            ev("click", seq=4, tag_name="span", region_type="tree",
               text="某市财政局", fieldid="tree_node_1", in_dialog=True,
               context=_ctx()),
            ev("click", seq=5, tag_name="span", region_type="tree",
               text="某市财政局", fieldid="tree_node_1", in_dialog=True,
               context=_ctx()),
        ]
        out = _preprocess_form_interactions(events)
        # 触发点击 + 两次树点击 → 仅一个合成 change，无残留树点击
        self.assertEqual([(e.seq, e.type) for e in out], [(2, "change")])

    def test_untriggered_tree_select_still_recorded(self):
        """找不到触发字段时，树选择本身仍应产出 tree.select 步骤。"""
        events = [
            ev("click", seq=1, tag_name="span", region_type="tree",
               text="某市财政局", fieldid="tree_node_1", in_dialog=True,
               context=_ctx()),
            ev("click", seq=2, tag_name="span", text="确定", in_dialog=True,
               context=_ctx()),
        ]
        steps = convert_events_to_steps(events)
        trees = [s for s in steps if s["component"] == "tree"]
        self.assertEqual(len(trees), 1)
        self.assertEqual(trees[0]["target"]["label"], "某市财政局")


# ════════════════════════════════════════════════════════════════
# 问题4真实形态：弹窗参照选择器（单选行）+ 无特征开关 —— 依据 2026-09-03
# 重新录制的 suite4.events.json（26 事件）复现
# ════════════════════════════════════════════════════════════════

_ROW_DATA = [
    {"column": "银行网点行号", "value": "621700000001"},
    {"column": "开户银行全称", "value": "中信银行"},
    {"column": "账号", "value": "20260712010000001"},
    {"column": "账户名称", "value": "账号20260712010000001名称"},
    {"column": "开户日期", "value": "2026-08-12"},
]


class TestPopupReferenceRadioIssue4(unittest.TestCase):
    """弹窗内参照选择器：触发图标 → popup_reference 弹窗 → 表格单选行 → 确定。"""

    def _events(self):
        return [
            ev("click", seq=9, tag_name="button",
               label_text="是否金库退付",
               fieldid="fkrxx_form_isRefundFromTreasury",
               in_dialog=True, is_reference_trigger=True,
               context=_ctx()),
            ev("click", seq=10, tag_name="button",
               label_text="是否金库退付",
               fieldid="fkrxx_form_isRefundFromTreasury",
               in_dialog=True, is_reference_trigger=True,
               context=_ctx()),
            ev("click", seq=11, tag_name="i", in_table=True,
               label_text="付款人全称", is_reference_trigger=True,
               fieldid="fkrxx_form_payAcctName_btn_icon",
               in_dialog=True, context=_ctx()),
            ev("click", seq=12, tag_name="i", in_table=True,
               label_text="付款人全称", is_reference_trigger=True,
               fieldid="fkrxx_form_payAcctName_btn_icon",
               in_dialog=True, context=_ctx()),
            ev("dialog_open", seq=13, in_dialog=True, context=_ctx()),
            ev("dialog_open", seq=14, in_dialog=True,
               is_popup_reference=True, context=_ctx()),
            ev("click", seq=15, tag_name="input", in_table=True,
               input_type="radio", name="table-radio",
               fieldid="fkrxx_form_payAcctName", in_dialog=True,
               value="2614234408488009749", row_data=list(_ROW_DATA),
               editable_row_number=1, context=_ctx()),
            ev("click", seq=16, tag_name="input", in_table=True,
               input_type="radio", name="table-radio",
               fieldid="fkrxx_form_payAcctName", in_dialog=True,
               value="2614234408488009749", row_data=list(_ROW_DATA),
               editable_row_number=1, context=_ctx()),
            ev("click", seq=17, tag_name="span", text="确定",
               fieldid="fkrxx_form_payAcctName_modal_ok",
               in_dialog=True, in_table=True, context=_ctx()),
            ev("click", seq=18, tag_name="span", text="确定",
               fieldid="fkrxx_form_payAcctName_modal_ok",
               in_dialog=True, in_table=True, context=_ctx()),
            ev("click", seq=19, tag_name="span", text="确定",
               fieldid="qd_btn", in_dialog=True,
               is_reference_trigger=True, context=_ctx()),
        ]

    def test_switch_fallback_synthesized(self):
        """JS 未识别 is_switch 且无 change 时，「是否*」重复点击合成 form.fill。"""
        out = _preprocess_form_interactions(self._events())
        changes = [e for e in out if e.type == "change"
                   and e.target.label_text == "是否金库退付"]
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].target.value, "true")
        # 两次开关点击都被消费
        self.assertNotIn(
            "是否金库退付",
            [e.target.label_text for e in out if e.type == "click"],
        )

    def test_radio_reference_lands_in_form_fill(self):
        """单选行选择合成 form.change，值记录行号结构化值（问题5）。

        内容值（如账号/单据号）每次运行动态生成，回放匹配必败；
        行号在同等数据准备下稳定。display_text 保留作可读性回退。
        """
        steps = convert_events_to_steps(self._events())
        fills = [s for s in steps if s["component"] == "form"
                 and s["operation"] == "fill"]
        self.assertEqual(len(fills), 1)
        fields = fills[0]["target"]["fields"]
        self.assertEqual(fields.get("是否金库退付"), "true")
        self.assertEqual(fields.get("付款人全称"), {"row_number": 1})

    def test_radio_reference_without_row_number_falls_back(self):
        """无行号信息时退回显示文本匹配（旧行为兼容）。"""
        events = self._events()
        for e in events:
            if e.target.input_type == "radio":
                e.target.editable_row_number = None
        steps = convert_events_to_steps(events)
        fills = [s for s in steps if s["component"] == "form"
                 and s["operation"] == "fill"]
        fields = fills[0]["target"]["fields"]
        self.assertEqual(fields.get("付款人全称"),
                         "账号20260712010000001名称")

    def test_both_confirms_present(self):
        """选择器确定（optional+fieldid）与外层确定都保留为独立步骤。"""
        steps = convert_events_to_steps(self._events())
        confirms = [s for s in steps if s["component"] == "dialog"
                    and s["operation"] == "confirm"]
        self.assertEqual(len(confirms), 2)
        first, second = confirms
        # 选择器自身确定：optional + fieldid 精确定位，回放时可跳过
        self.assertEqual(first["target"]["fieldid"],
                         "fkrxx_form_payAcctName_modal_ok")
        self.assertTrue(first["target"]["optional"])
        # 外层确定：普通步骤（无可选标志）
        self.assertNotIn("optional", second["target"])
        self.assertEqual(second["target"]["label"], "确定")

    def test_no_radio_click_leftover(self):
        """两次单选行点击都被消费，不残留 table_row_selection/dialog.click。"""
        steps = convert_events_to_steps(self._events())
        comps = [(s["component"], s["operation"]) for s in steps]
        self.assertNotIn(("table_row_selection", "select"), comps)
        self.assertNotIn(("dialog", "click"), comps)


    def test_switch_with_captured_state_uses_it(self):
        """JS 捕获了开关状态值（is_switch=True + value）时优先使用。"""
        from ydf_recorder.registry import _build_form
        event = ev("click", seq=1, tag_name="button", is_switch=True,
                   label_text="是否金库退付", value="false",
                   fieldid="fkrxx_form_x", context=_ctx())
        self.assertEqual(_build_form("fill", [event]),
                         {"fields": {"是否金库退付": "false"}})

    def test_toolbar_unaffected_by_relaxed_trigger(self):
        """参照图标触发放宽不影响普通页面 toolbar 识别。"""
        events = [
            ev("click", seq=1, tag_name="i", in_table=True,
               label_text="付款人全称", is_reference_trigger=True,
               fieldid="fkrxx_form_payAcctName_btn_icon", context=_ctx()),
            ev("dialog_open", seq=2, context=_ctx()),
            ev("click", seq=3, tag_name="span",
               region_type="top_action_bar", text="生成凭证",
               fieldid="create_btn", context=_ctx()),
        ]
        steps = convert_events_to_steps(events)
        self.assertIn("生成凭证",
                      [str((s.get("target") or {}).get("label"))
                       for s in steps if s["component"] == "toolbar"])


class TestRowNumberOverMatchIssue5(unittest.TestCase):
    """问题5：行选择记录行号而非内容值（单据号动态生成，内容匹配回放必败）。"""

    def test_table_row_selection_prefers_row_number(self):
        """有 editable_row_number 时优先输出 row_number，而非 match:{申请单号}。"""
        from ydf_recorder.registry import _build_table_row_selection
        event = ev("click", seq=3, tag_name="input", in_table=True,
                   input_type="checkbox", fieldid="first_table_checkbox",
                   row_data=[{"column": "申请单号", "value": "ZJBKVOU202600002096"},
                             {"column": "预算年度", "value": "2026"}],
                   editable_row_number=1, context=_ctx())
        target = _build_table_row_selection("select", [event])
        self.assertEqual(target, {"row_number": 1})

    def test_table_row_selection_falls_back_to_match(self):
        """无行号信息时回退到内容 match（旧行为兼容）。"""
        from ydf_recorder.registry import _build_table_row_selection
        event = ev("click", seq=3, tag_name="input", in_table=True,
                   input_type="checkbox", fieldid="first_table_checkbox",
                   row_data=[{"column": "申请单号", "value": "ZJBKVOU202600002096"},
                             {"column": "预算年度", "value": "2026"}],
                   context=_ctx())
        target = _build_table_row_selection("select", [event])
        self.assertEqual(target,
                         {"match": {"column": "申请单号",
                                    "equals": "ZJBKVOU202600002096"}})

    def test_td_checkbox_click_with_row_number(self):
        """问题5真实场景：点 checkbox 单元格 td（非 input），JS 兜底提取行号后
        table_row_selection 应输出 row_number 而非 match:{申请单号}。"""
        steps = convert_events_to_steps([
            ev("click", seq=1, tag_name="td", in_table=True,
               region_type="main_table", fieldid="checkbox",
               row_data=[{"column": "申请单号", "value": "ZJBKVOU202600002096"}],
               row_text="1 ZJBKVOU202600002096 2026",
               editable_row_number=1, context=_ctx()),
            ev("click", seq=2, tag_name="td", in_table=True,
               region_type="main_table", fieldid="checkbox",
               row_data=[{"column": "申请单号", "value": "ZJBKVOU202600002096"}],
               editable_row_number=1, context=_ctx()),
            ev("click", seq=3, tag_name="span",
               region_type="top_action_bar", text="补充付款人",
               fieldid="bcfkr_btn", context=_ctx()),
        ])
        selections = [s for s in steps if s["component"] == "table_row_selection"]
        self.assertEqual(len(selections), 1)
        self.assertEqual(selections[0]["target"], {"row_number": 1})

    def test_row_number_target_passes_dsl_validation(self):
        """row_number-only target 通过 ydf-browser DSL 校验。"""
        ydf_browser = Path(__file__).resolve().parents[2] / "ydf-browser"
        if str(ydf_browser) not in sys.path:
            sys.path.insert(0, str(ydf_browser))
        from ydf_browser.dsl import _validate_steps
        from ydf_browser.models import ActionStep
        steps = [ActionStep(kind="component", component="table_row_selection",
                            operation="select",
                            target={"row_number": 1})]
        _validate_steps(steps, "test.yaml")  # 不抛异常即通过

    def test_form_fill_row_number_value_passes_dsl_validation(self):
        """form.fill 字段的结构化行号值通过 ydf-browser DSL 校验。"""
        ydf_browser = Path(__file__).resolve().parents[2] / "ydf-browser"
        if str(ydf_browser) not in sys.path:
            sys.path.insert(0, str(ydf_browser))
        from ydf_browser.dsl import _validate_steps
        from ydf_browser.models import ActionStep
        steps = [ActionStep(kind="component", component="form",
                            operation="fill",
                            target={"fields": {"付款人全称": {"row_number": 1}}})]
        _validate_steps(steps, "test.yaml")  # 不抛异常即通过
