"""flatTree 反查增强（设计器运行时元数据通道）回归测试。

覆盖：
  - inject.js 注入脚本包含 flatTree 反查函数与全局调试入口
  - RecordedEventTarget 新增 uidata_* 字段且 from_dict 正确透传/降级
  - RECORDER_JS 为合法 JS 语法（有 node 时执行 node --check）
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ydf_recorder.inject import RECORDER_JS  # noqa: E402
from ydf_recorder.models import RecordedEvent, RecordedEventTarget  # noqa: E402


class TestRecorderJsContainsUidataLookup(unittest.TestCase):
    """注入脚本应包含 flatTree 反查通道的关键函数与映射表。"""

    REQUIRED_SNIPPETS = [
        "function getRuntimeFlatTree",
        "function findUidataNode",
        "function getUidataInfo",
        "function buildFieldidSelector",
        "YDF_NAME_WIDGET_TYPE",
        "window.__ydf_recorder_uidata_status",
        "uidata_name:",
        "uidata_container_path:",
        "window.YonDiFGlobal",
    ]

    def test_required_snippets_present(self):
        for snippet in self.REQUIRED_SNIPPETS:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, RECORDER_JS)

    def test_extract_target_emits_uidata_fields(self):
        # extractTarget 的返回对象应携带全部 5 个 uidata 字段
        for field in (
            "uidata_name",
            "uidata_node_type",
            "uidata_label",
            "uidata_div_code",
            "uidata_container_path",
        ):
            with self.subTest(field=field):
                self.assertIn(f"{field}: uidataInfo", RECORDER_JS)

    def test_heuristic_miss_falls_back_to_uidata(self):
        # detectWidgetType 启发式兜底应经 getUidataInfo + 注册名映射
        self.assertIn("YDF_NAME_WIDGET_TYPE[ui.name]", RECORDER_JS)

    def test_build_selector_uses_disambiguation(self):
        self.assertIn("return buildFieldidSelector(el, fid);", RECORDER_JS)


class TestModelsPassThrough(unittest.TestCase):
    """RecordedEventTarget 新增 uidata_* 字段的透传与降级。"""

    def test_from_dict_passes_uidata_fields(self):
        raw = {
            "seq": 1,
            "timestamp": 100,
            "type": "click",
            "target": {
                "fieldid": "billCard",
                "uidata_name": "YDFReferSelect",
                "uidata_node_type": "formItem",
                "uidata_label": "预算单位",
                "uidata_div_code": "budgetUnit",
                "uidata_container_path": ["rootDiv", "cardA", "tab1"],
            },
            "context": {"url": "http://test", "title": "t"},
            "meta": {"frame_url": "http://test", "is_trusted": True},
        }
        event = RecordedEvent.from_dict(raw)
        self.assertEqual(event.target.uidata_name, "YDFReferSelect")
        self.assertEqual(event.target.uidata_node_type, "formItem")
        self.assertEqual(event.target.uidata_label, "预算单位")
        self.assertEqual(event.target.uidata_div_code, "budgetUnit")
        self.assertEqual(event.target.uidata_container_path, ["rootDiv", "cardA", "tab1"])

    def test_from_dict_without_uidata_defaults_none(self):
        raw = {
            "seq": 2,
            "timestamp": 100,
            "type": "click",
            "target": {"fieldid": "x"},
            "context": {"url": "http://test", "title": "t"},
            "meta": {"frame_url": "http://test", "is_trusted": True},
        }
        event = RecordedEvent.from_dict(raw)
        self.assertIsNone(event.target.uidata_name)
        self.assertIsNone(event.target.uidata_container_path)

    def test_unknown_uidata_keys_are_filtered(self):
        # from_dict 白名单过滤：JS 侧多出的字段不应导致构造失败
        raw = {
            "seq": 3,
            "timestamp": 100,
            "type": "click",
            "target": {"fieldid": "x", "uidata_future_field": "whatever"},
            "context": {"url": "http://test", "title": "t"},
            "meta": {"frame_url": "http://test", "is_trusted": True},
        }
        event = RecordedEvent.from_dict(raw)
        self.assertEqual(event.target.fieldid, "x")

    def test_container_path_type_is_list(self):
        target = RecordedEventTarget(uidata_container_path=["a", "b"])
        d = target.to_dict()
        self.assertIsInstance(d["uidata_container_path"], list)
        self.assertEqual(d["uidata_container_path"], ["a", "b"])


@unittest.skipIf(shutil.which("node") is None, "node 不可用，跳过 JS 语法检查")
class TestRecorderJsSyntax(unittest.TestCase):
    """RECORDER_JS 应是语法合法的 JS（防止编辑引入语法错误）。"""

    def test_node_check(self):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
            fh.write(RECORDER_JS)
            path = fh.name
        try:
            result = subprocess.run(
                ["node", "--check", path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(
                result.returncode,
                0,
                f"RECORDER_JS 语法错误:\n{result.stderr}",
            )
        finally:
            Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
