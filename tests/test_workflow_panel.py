"""workflow_panel 与 table.assert_columns 识别测试。

覆盖：
  - workflow_panel.click（ydf-browser 0.1.42 新增组件）：面板动作区点击识别与
    target 构建（{label: 完整可见文字}）
  - workflow_result 优先级回归：结果层标志存在时不被 workflow_panel 抢走
  - table.assert_columns：Alt+点击列头检查点 → 列存在性断言（{present: [列名]}）
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
from ydf_recorder.registry import (  # noqa: E402
    build_target,
    classify_event,
)


def ev(etype: str, seq: int = 1, timestamp: int = 100, **target_kwargs) -> RecordedEvent:
    return RecordedEvent(
        type=etype,
        seq=seq,
        timestamp=timestamp,
        target=RecordedEventTarget(**target_kwargs),
        context=RecordedEventContext(url="http://test", title="测试"),
    )


class TestWorkflowPanel(unittest.TestCase):
    """workflow_panel.click：工作流操作面板动作识别。"""

    def test_panel_button_click(self):
        event = ev("click", text="撤回审批", is_workflow_panel=True,
                   tag_name="button")
        self.assertEqual(classify_event(event), ("workflow_panel", "click"))

    def test_panel_target_label(self):
        event = ev("click", text="撤回审批", is_workflow_panel=True,
                   tag_name="button")
        target = build_target("workflow_panel", "click", [event])
        self.assertEqual(target, {"label": "撤回审批"})

    def test_panel_label_falls_back_to_label_text(self):
        event = ev("click", text=None, label_text="驳回", is_workflow_panel=True,
                   tag_name="button")
        target = build_target("workflow_panel", "click", [event])
        self.assertEqual(target, {"label": "驳回"})

    def test_panel_radio_label_click(self):
        # 面板内单选式操作项（label / [role=radio]）
        event = ev("click", text="同意并退回", is_workflow_panel=True,
                   tag_name="label")
        self.assertEqual(classify_event(event), ("workflow_panel", "click"))

    def test_non_action_area_click_not_panel(self):
        # 面板外（审批历史/评论区/背景工具栏）点击不标记 → 不识别
        event = ev("click", text="审批历史", is_workflow_panel=False,
                   tag_name="div")
        pair = classify_event(event)
        self.assertNotEqual(pair, ("workflow_panel", "click"))

    def test_empty_label_click_not_recognized(self):
        event = ev("click", text="", label_text=None, is_workflow_panel=True,
                   tag_name="button")
        self.assertIsNone(classify_event(event))

    def test_result_layer_still_wins_when_both_flags(self):
        # 面板内点击同时命中结果层文本时，workflow_result（注册在前）优先
        event = ev("click", text="确认", is_workflow_result=True,
                   workflow_result_text="提交请求已执行完毕 总数 1 成功 1 条",
                   is_workflow_panel=True, tag_name="button")
        self.assertEqual(classify_event(event), ("workflow_result", "confirm"))

    def test_input_events_in_panel_not_click(self):
        event = ev("input", text="撤回审批", is_workflow_panel=True,
                   tag_name="input")
        self.assertNotEqual(classify_event(event), ("workflow_panel", "click"))


class TestTableAssertColumnsCheckpoint(unittest.TestCase):
    """Alt+点击列头 → table.assert_columns {present: [列名]}。"""

    def test_header_checkpoint_classified(self):
        event = ev("checkpoint", in_table=True, in_table_header=True,
                   column_header="项目名称", tag_name="th")
        self.assertEqual(classify_event(event), ("table", "assert_columns"))

    def test_header_checkpoint_target(self):
        event = ev("checkpoint", in_table=True, in_table_header=True,
                   column_header="项目名称", tag_name="th")
        target = build_target("table", "assert_columns", [event])
        self.assertEqual(target, {"present": ["项目名称"]})

    def test_header_without_column_falls_through(self):
        # 表头点击但未提取到列名 → 不走 assert_columns，落到后续分流
        event = ev("checkpoint", in_table=True, in_table_header=True,
                   column_header=None, tag_name="th")
        self.assertNotEqual(classify_event(event), ("table", "assert_columns"))

    def test_body_cell_still_assert_row_values(self):
        # 回归：行内检查点仍走 assert_row_values
        event = ev("checkpoint", in_table=True, in_table_header=False,
                   row_data=[{"column": "项目代码", "value": "P001"}],
                   cell_text="P001", column_header="项目代码", tag_name="td")
        self.assertEqual(classify_event(event), ("table", "assert_row_values"))


if __name__ == "__main__":
    unittest.main()
