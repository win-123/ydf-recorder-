"""租户匹配（名称/ID/编码）与菜单模糊兜底回归。

背景（2026-10-29 用户反馈）：向导里填的租户是 tenantId（如 knznywua），
而 _find_tenant_id 只按名称匹配 → 上下文切换失败 → 菜单树拉到默认租户的
→ 目标菜单解析不到 → 自动开菜单失败，浏览器停在门户页。
"""

import unittest

from ydf_recorder.auth import _find_tenant_id
from ydf_recorder.menu import resolve_menu_to_service_code


TENANT_PAYLOAD = {
    "status": 1,
    "data": {
        "tenants": [
            {"tenantId": "knznywua", "tenantName": "财政一体化", "tenantCode": None},
            {"tenantId": "ppksggwz", "tenantName": "供销平台", "tenantCode": "GX01"},
        ]
    },
}


def _tree(leaf_code: str = "svc-1") -> dict:
    return {
        "data": [
            {
                "menuBarMultiLangText": {"zh_CN": "项目库"},
                "menuItems": [
                    {
                        "multiLangText": {"zh_CN": "一级项目"},
                        "children": [
                            {
                                "multiLangText": {"zh_CN": "一级项目管理（财政）"},
                                "serviceCode": leaf_code,
                            },
                            {
                                "multiLangText": {"zh_CN": "一级项目管理（财务）"},
                                "serviceCode": "svc-2",
                            },
                        ],
                    }
                ],
            }
        ]
    }


class TestTenantMatching(unittest.TestCase):
    def test_match_by_name(self):
        self.assertEqual(_find_tenant_id(TENANT_PAYLOAD, "财政一体化"), "knznywua")

    def test_match_by_id(self):
        self.assertEqual(_find_tenant_id(TENANT_PAYLOAD, "knznywua"), "knznywua")

    def test_match_by_code(self):
        self.assertEqual(_find_tenant_id(TENANT_PAYLOAD, "GX01"), "ppksggwz")

    def test_no_match(self):
        self.assertEqual(_find_tenant_id(TENANT_PAYLOAD, "不存在"), "")


class TestMenuFuzzy(unittest.TestCase):
    def test_exact_full_path(self):
        self.assertEqual(
            resolve_menu_to_service_code(_tree(), "项目库>>一级项目>>一级项目管理（财政）"),
            "svc-1",
        )

    def test_fuzzy_leaf_raw_exact(self):
        # 跨环境多写了一级前缀，末级名原始值可唯一命中
        self.assertEqual(
            resolve_menu_to_service_code(_tree(), "预算管理>>项目库>>一级项目管理（财政）"),
            "svc-1",
        )

    def test_fuzzy_normalized_leaf(self):
        # 归一化后（财政）/（财务）撞车 → 应报多候选而不是误选
        with self.assertRaises(ValueError) as ctx:
            resolve_menu_to_service_code(_tree(), "项目库>>一级项目管理")
        self.assertIn("多个候选", str(ctx.exception))

    def test_fuzzy_normalized_leaf_unique(self):
        tree = _tree()
        del tree["data"][0]["menuItems"][0]["children"][1]  # 只留（财政）一个叶子
        self.assertEqual(
            resolve_menu_to_service_code(tree, "项目库>>一级项目管理"),
            "svc-1",
        )

    def test_fuzzy_multiple_candidates_raise(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_menu_to_service_code(_tree(), "项目库>>一级项目管理")
        self.assertIn("多个候选", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
