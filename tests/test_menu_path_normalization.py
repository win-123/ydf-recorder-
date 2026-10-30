"""菜单路径规范化回归（录制写规范路径 + 回放前自愈）。

背景（2026-10-29 用户反馈"回放错误"）：
  录制时向导填的是「预算管理>>项目库>>一级项目管理（财政）」（界面层级，且漏了
  「一级项目」一层），录制端模糊匹配能定位到 serviceCode，但写进 DSL 的仍是
  用户手填路径；回放端 ``ydf_browser.gateway.resolve_menu`` 是**后缀精确匹配**，
  于是第一步 open_menu 就报「未找到菜单」，退出码 1。
"""

import unittest

from ydf_recorder.menu import resolve_menu_target, resolve_menu_to_service_code
from ydf_recorder.converter import dedupe_repeated_fills
from ydf_recorder.replay import (
    extract_menu_paths,
    rewrite_menu_paths,
)


MENU_TREE = {
    "data": [
        {
            "menuBarMultiLangText": {"zh_CN": "项目库"},
            "menuItems": [
                {
                    "multiLangText": {"zh_CN": "系统设置"},
                    "children": [
                        {
                            "multiLangText": {"zh_CN": "项目目录管理"},
                            "serviceCode": "svc-dir",
                        }
                    ],
                },
                {
                    "multiLangText": {"zh_CN": "一级项目"},
                    "children": [
                        {
                            "multiLangText": {"zh_CN": "一级项目管理（财政）"},
                            "serviceCode": "svc-fin",
                        },
                        {
                            "multiLangText": {"zh_CN": "一级项目管理（财务）"},
                            "serviceCode": "svc-cw",
                        },
                    ],
                },
            ],
        }
    ]
}


class ResolveMenuTargetTest(unittest.TestCase):
    def test_exact_path_returns_canonical(self) -> None:
        result = resolve_menu_target(MENU_TREE, "项目库>>一级项目>>一级项目管理（财政）")
        self.assertEqual(result.service_code, "svc-fin")
        self.assertEqual(result.path, "项目库>>一级项目>>一级项目管理（财政）")
        self.assertEqual(result.matched_by, "exact")

    def test_ui_level_path_is_resolved_to_tree_path(self) -> None:
        """界面层级（预算管理>>项目库>>…）漏层时，仍要拿到菜单树真实路径。"""
        result = resolve_menu_target(MENU_TREE, "预算管理>>项目库>>一级项目管理（财政）")
        self.assertEqual(result.service_code, "svc-fin")
        self.assertEqual(result.path, "项目库>>一级项目>>一级项目管理（财政）")
        self.assertEqual(result.matched_by, "raw_leaf")

    def test_legacy_wrapper_still_returns_service_code(self) -> None:
        self.assertEqual(
            resolve_menu_to_service_code(MENU_TREE, "预算管理>>项目库>>一级项目管理（财政）"),
            "svc-fin",
        )

    def test_parentheses_still_discriminate(self) -> None:
        """（财政）/（财务）不能被归一化吞掉，必须各归各。"""
        self.assertEqual(
            resolve_menu_target(MENU_TREE, "项目库>>一级项目>>一级项目管理（财务）").service_code,
            "svc-cw",
        )


class RewriteMenuPathsTest(unittest.TestCase):
    DSL = (
        "suite:\n"
        "  code: s1\n"
        "cases:\n"
        "- code: c1\n"
        "  steps:\n"
        "  - action: open_menu\n"
        "    menu_path: 预算管理>>项目库>>一级项目管理（财政）\n"
        "  - action: open_menu\n"
        "    menu_path: '项目库>>一级项目>>一级项目管理（财务）'\n"
    )

    def test_extract_paths_in_order(self) -> None:
        self.assertEqual(
            extract_menu_paths(self.DSL),
            [
                "预算管理>>项目库>>一级项目管理（财政）",
                "项目库>>一级项目>>一级项目管理（财务）",
            ],
        )

    def test_rewrite_preserves_indent_and_quotes(self) -> None:
        text, changes = rewrite_menu_paths(
            self.DSL,
            {"预算管理>>项目库>>一级项目管理（财政）": "项目库>>一级项目>>一级项目管理（财政）"},
        )
        self.assertEqual(
            changes,
            [("预算管理>>项目库>>一级项目管理（财政）", "项目库>>一级项目>>一级项目管理（财政）")],
        )
        self.assertIn(
            "    menu_path: 项目库>>一级项目>>一级项目管理（财政）\n", text
        )
        # 未命中映射的行（带引号那条）原样保留
        self.assertIn("    menu_path: '项目库>>一级项目>>一级项目管理（财务）'\n", text)

    def test_rewrite_keeps_quotes_when_original_quoted(self) -> None:
        dsl = "    menu_path: \"旧路径\"\n"
        text, changes = rewrite_menu_paths(dsl, {"旧路径": "新>>路径"})
        self.assertEqual(changes, [("旧路径", "新>>路径")])
        self.assertEqual(text, '    menu_path: "新>>路径"\n')

    def test_no_mapping_no_change(self) -> None:
        text, changes = rewrite_menu_paths(self.DSL, {"不存在": "x"})
        self.assertEqual(changes, [])
        self.assertEqual(text, self.DSL)


def _fill(fields: dict) -> dict:
    return {"component": "form", "operation": "fill", "target": {"fields": fields}}


def _click(label: str) -> dict:
    return {"component": "toolbar", "operation": "click", "target": {"label": label}}


class DedupeRepeatedFillsTest(unittest.TestCase):
    def test_trailing_identical_refill_and_save_are_dropped(self) -> None:
        """保存后再同值重填同一字段 + 再保存 → 两步噪音都应去掉。"""
        steps = [
            _fill({"项目目录": "998", "项目名称": "录制测试", "项目概述": "录制测试"}),
            _click("保存"),
            _fill({"项目概述": "录制测试"}),
            _click("保存"),
        ]
        out = dedupe_repeated_fills(steps)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["target"]["fields"]["项目概述"], "录制测试")
        self.assertEqual(out[1]["target"]["label"], "保存")

    def test_changed_value_refill_is_kept(self) -> None:
        """改值重填是真实意图，必须保留。"""
        steps = [
            _fill({"项目概述": "旧值"}),
            _click("保存"),
            _fill({"项目概述": "新值"}),
            _click("保存"),
        ]
        out = dedupe_repeated_fills(steps)
        self.assertEqual(len(out), 4)
        self.assertEqual(out[2]["target"]["fields"]["项目概述"], "新值")

    def test_new_field_in_refill_is_trimmed_not_dropped(self) -> None:
        """重填里含新字段 → 只剔除同值键，保留新字段。"""
        steps = [
            _fill({"项目概述": "a"}),
            _click("保存"),
            _fill({"项目概述": "a", "备注": "b"}),
            _click("保存"),
        ]
        out = dedupe_repeated_fills(steps)
        self.assertEqual(len(out), 4)
        self.assertEqual(out[2]["target"]["fields"], {"备注": "b"})

    def test_non_save_repeated_clicks_are_kept(self) -> None:
        """连续「新增」等非保存类点击不去重（可能是合法的两次打开弹窗）。"""
        steps = [_click("新增"), _click("新增")]
        self.assertEqual(dedupe_repeated_fills(steps), steps)

    def test_plain_case_untouched(self) -> None:
        steps = [
            _fill({"a": "1"}),
            _click("保存"),
        ]
        self.assertEqual(dedupe_repeated_fills(steps), steps)


if __name__ == "__main__":
    unittest.main()

