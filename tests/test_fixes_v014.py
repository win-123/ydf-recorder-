"""v0.1.4 三项修复的回归测试。

覆盖：
  - #3 workflow_result 裸 confirm/details 自动补 assert（0.1.42 前置约束）
  - #4 replay 运行时版本校验（_version_tuple / query_runtime_version / check_runtime_version）
  - #8 suite 不再输出 requires_runtime_serial 噪音字段
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ydf_recorder.models import (  # noqa: E402
    RecordedEvent,
    RecordedEventContext,
    RecordedEventTarget,
)
from ydf_recorder.converter import convert_events_to_steps  # noqa: E402
from ydf_recorder.dsl_models import DslTestSuite  # noqa: E402
from ydf_recorder.replay import (  # noqa: E402
    _version_tuple,
    check_runtime_version,
    query_runtime_version,
)


def ev(etype: str, seq: int = 1, timestamp: int = 100, context=None, **target_kwargs) -> RecordedEvent:
    return RecordedEvent(
        type=etype,
        seq=seq,
        timestamp=timestamp,
        target=RecordedEventTarget(**target_kwargs),
        context=context or RecordedEventContext(url="http://test", title="测试"),
    )


WF_TEXT = "提交请求已执行完毕 总数 3 成功 2 条 失败 1 条"
WF = dict(is_workflow_result=True, workflow_result_text=WF_TEXT)


class TestWorkflowResultAutoAssert(unittest.TestCase):
    """#3：裸 confirm/details 前自动补 workflow_result.assert。"""

    def test_bare_confirm_gets_assert(self):
        steps = convert_events_to_steps([
            ev("click", seq=1, text="确认", **WF),
        ])
        ops = [(s.get("component"), s.get("operation")) for s in steps]
        self.assertIn(("workflow_result", "assert"), ops)
        # assert 必须在 confirm 之前
        self.assertLess(ops.index(("workflow_result", "assert")), ops.index(("workflow_result", "confirm")))
        # assert 的统计数字来自结果层文本解析（非编造）
        assert_step = steps[ops.index(("workflow_result", "assert"))]
        self.assertEqual(assert_step["target"], {"total": 3, "succeeded": 2, "failed": 1})

    def test_bare_details_gets_assert(self):
        steps = convert_events_to_steps([
            ev("click", seq=1, text="查看详情", **WF),
        ])
        ops = [(s.get("component"), s.get("operation")) for s in steps]
        self.assertIn(("workflow_result", "assert"), ops)
        self.assertLess(ops.index(("workflow_result", "assert")), ops.index(("workflow_result", "details")))

    def test_explicit_assert_not_duplicated(self):
        steps = convert_events_to_steps([
            ev("checkpoint", seq=1, text=WF_TEXT, **WF),
            ev("click", seq=2, text="确认", **WF),
        ])
        ops = [(s.get("component"), s.get("operation")) for s in steps]
        self.assertEqual(ops.count(("workflow_result", "assert")), 1)

    def test_unparseable_confirm_no_assert_but_warns(self):
        evs = [ev("click", seq=1, text="确认", is_workflow_result=True, workflow_result_text="操作完成")]
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            steps = convert_events_to_steps(evs)
        ops = [(s.get("component"), s.get("operation")) for s in steps]
        self.assertNotIn(("workflow_result", "assert"), ops)
        self.assertIn(("workflow_result", "confirm"), ops)
        self.assertIn("WorkflowResultError", err.getvalue())

    def test_assert_flag_resets_across_sessions(self):
        # 一次结果层会话（有断言）→ 中间插入其他步骤 → 新的裸 confirm 应再补断言
        steps = convert_events_to_steps([
            ev("checkpoint", seq=1, text=WF_TEXT, **WF),
            ev("click", seq=2, text="确认", **WF),
            ev("click", seq=3, text="保存", tag_name="button"),
            ev("click", seq=4, text="确认", **WF),
        ])
        ops = [(s.get("component"), s.get("operation")) for s in steps]
        self.assertEqual(ops.count(("workflow_result", "assert")), 2)


class TestRuntimeVersionCheck(unittest.TestCase):
    """#4：运行时版本校验纯函数。"""

    def test_version_tuple(self):
        self.assertEqual(_version_tuple("0.1.42"), (0, 1, 42))
        self.assertLess(_version_tuple("0.1.9"), _version_tuple("0.1.42"))
        self.assertLessEqual(_version_tuple("0.1.42-beta"), _version_tuple("0.1.42"))
        self.assertGreater(_version_tuple("0.2.0"), _version_tuple("0.1.42"))

    def _runtime_root(self, version: str | None) -> Path:
        tmp = tempfile.mkdtemp(prefix="ydf-rt-")
        base = Path(tmp) / ".ydf-browser-runtime"
        base.mkdir()
        if version is not None:
            (base / ".ydf-browser-version").write_text(version + "\n", encoding="utf-8")
        return Path(tmp)

    def test_marker_version_ok(self):
        root = self._runtime_root("0.1.42")
        self.assertEqual(query_runtime_version(root), "0.1.42")
        self.assertIsNone(check_runtime_version(root))

    def test_marker_version_too_old(self):
        root = self._runtime_root("0.1.16")
        self.assertIn("低于最低要求", check_runtime_version(root) or "")

    def test_no_runtime_no_warning(self):
        # 未使用内嵌运行时（无 venv 无标记）→ 不告警
        with tempfile.TemporaryDirectory(prefix="ydf-empty-") as tmp:
            self.assertIsNone(check_runtime_version(Path(tmp)))
            self.assertIsNone(query_runtime_version(Path(tmp)))


class TestSuiteOutputCleanup(unittest.TestCase):
    """#8：suite 不再输出 requires_runtime_serial。"""

    def test_omitted_when_false(self):
        suite = DslTestSuite(code="s", name="n", tenant="t")
        self.assertNotIn("requires_runtime_serial", suite.to_dict())

    def test_kept_when_true(self):
        suite = DslTestSuite(code="s", name="n", requires_runtime_serial=True)
        self.assertTrue(suite.to_dict()["requires_runtime_serial"])


if __name__ == "__main__":
    unittest.main()
