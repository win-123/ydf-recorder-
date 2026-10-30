"""GUI 配置存储层测试（多环境配置 CRUD + 变量解析 + 内置变量清单）。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from ydf_recorder import gui_config as store


class ConfigPathTest(unittest.TestCase):
    def test_respects_env_override(self):
        old = os.environ.get("YDF_RECORDER_CONFIG")
        os.environ["YDF_RECORDER_CONFIG"] = "/tmp/custom-env.yaml"
        try:
            self.assertEqual(store.config_path(), Path("/tmp/custom-env.yaml"))
        finally:
            if old is None:
                os.environ.pop("YDF_RECORDER_CONFIG", None)
            else:
                os.environ["YDF_RECORDER_CONFIG"] = old


class DocumentRoundTripTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "env.yaml"

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_missing_returns_skeleton(self):
        doc = store.load_document(self.path)
        self.assertEqual(doc, {"environments": {}})

    def test_save_and_load_preserves_unknown_keys(self):
        doc = {
            "environments": {
                "生产": {
                    "base_url": "http://10.16.30.53",
                    "tenant": "财政一体化",
                    "username": "15500100111",
                    "users": {"张三": {"username": "u1", "password": "p1"}},
                    "endpoints": {"service_tree": "/x"},
                    "sysid": "yonbip",
                }
            }
        }
        store.save_document(doc, self.path)
        loaded = store.load_document(self.path)
        profile = store.get_profile(loaded, "生产")
        self.assertEqual(profile["users"]["张三"]["username"], "u1")
        self.assertEqual(profile["endpoints"]["service_tree"], "/x")
        self.assertEqual(profile["sysid"], "yonbip")

    def test_file_mode_is_private(self):
        store.save_document({"environments": {}}, self.path)
        mode = self.path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)


class ProfileCrudTest(unittest.TestCase):
    def setUp(self):
        self.doc = {"environments": {}}

    def test_upsert_create_and_update(self):
        store.upsert_profile(
            self.doc,
            "生产",
            {"base_url": "http://a", "tenant": "T1", "default_org": "1", "username": "u"},
        )
        self.assertEqual(store.list_profiles(self.doc), ["生产"])
        store.upsert_profile(self.doc, "生产", {"base_url": "http://b"})
        profile = store.get_profile(self.doc, "生产")
        self.assertEqual(profile["base_url"], "http://b")
        # 未提交的字段保持原值
        self.assertEqual(profile["tenant"], "T1")

    def test_upsert_clears_empty_field(self):
        store.upsert_profile(self.doc, "生产", {"base_url": "http://a", "fiscal_year": "2026"})
        store.upsert_profile(self.doc, "生产", {"fiscal_year": ""})
        self.assertNotIn("fiscal_year", store.get_profile(self.doc, "生产"))

    def test_multiple_profiles_kept_separately(self):
        store.upsert_profile(self.doc, "生产", {"base_url": "http://prod"})
        store.upsert_profile(self.doc, "测试", {"base_url": "http://test"})
        self.assertEqual(store.list_profiles(self.doc), ["生产", "测试"])
        self.assertEqual(store.get_profile(self.doc, "生产")["base_url"], "http://prod")
        self.assertEqual(store.get_profile(self.doc, "测试")["base_url"], "http://test")

    def test_rename_keeps_advanced_keys(self):
        store.upsert_profile(self.doc, "旧名", {"base_url": "http://a"})
        self.doc["environments"]["旧名"]["sysid"] = "custom"
        store.upsert_profile(self.doc, "新名", {"base_url": "http://a"}, rename_from="旧名")
        self.assertEqual(store.list_profiles(self.doc), ["新名"])
        self.assertEqual(store.get_profile(self.doc, "新名")["sysid"], "custom")

    def test_delete(self):
        store.upsert_profile(self.doc, "生产", {"base_url": "http://a"})
        store.delete_profile(self.doc, "生产")
        self.assertEqual(store.list_profiles(self.doc), [])

    def test_duplicate_is_deep_copy(self):
        store.upsert_profile(self.doc, "生产", {"base_url": "http://a"})
        self.doc["environments"]["生产"]["variables"] = {"k": {"x": "1"}}
        store.duplicate_profile(self.doc, "生产", "生产_副本")
        self.doc["environments"]["生产_副本"]["variables"]["k"]["x"] = "2"
        self.assertEqual(
            store.get_profile(self.doc, "生产")["variables"]["k"]["x"], "1"
        )

    def test_duplicate_rejects_existing_name(self):
        store.upsert_profile(self.doc, "生产", {"base_url": "http://a"})
        with self.assertRaises(ValueError):
            store.duplicate_profile(self.doc, "生产", "生产")


class ValidateProfileTest(unittest.TestCase):
    def test_missing_required_fields(self):
        errors = store.validate_profile({"base_url": "", "tenant": "", "default_org": "", "username": ""})
        joined = " ".join(errors)
        self.assertIn("环境地址", joined)
        self.assertIn("租户", joined)
        self.assertIn("默认组织", joined)
        self.assertIn("登录用户名", joined)

    def test_bad_scheme(self):
        errors = store.validate_profile(
            {"base_url": "10.16.30.53", "tenant": "t", "default_org": "1", "username": "u"}
        )
        self.assertTrue(any("http" in item for item in errors))

    def test_valid(self):
        errors = store.validate_profile(
            {
                "base_url": "http://10.16.30.53",
                "tenant": "财政一体化",
                "default_org": "101001",
                "username": "15500100111",
            }
        )
        self.assertEqual(errors, [])


class VariableLinesTest(unittest.TestCase):
    def test_parse_nested(self):
        variables = store.parse_variable_lines(
            "files.预算表_xlsx=/Users/me/预算表.xlsx\n# 注释\napp.tenant=财政一体化"
        )
        self.assertEqual(variables["files"]["预算表_xlsx"], "/Users/me/预算表.xlsx")
        self.assertEqual(variables["app"]["tenant"], "财政一体化")

    def test_reject_bad_line(self):
        with self.assertRaises(ValueError):
            store.parse_variable_lines("没有等号的一行")

    def test_reject_random_namespace(self):
        with self.assertRaises(ValueError):
            store.parse_variable_lines("random.x=1")

    def test_round_trip(self):
        text = "files.a_pdf=/tmp/a.pdf\napp.org=101"
        self.assertEqual(store.format_variable_lines(store.parse_variable_lines(text)).split("\n"), sorted(text.split("\n")))


class BuiltinVariablesTest(unittest.TestCase):
    def test_lists_random_and_files(self):
        names = [item["name"] for item in store.BUILTIN_VARIABLES]
        self.assertIn("{{random.suffix}}", names)
        self.assertIn("{{random.mobile}}", names)
        self.assertIn("{{files.<文件名>}}", names)

    def test_every_entry_has_sample_and_desc(self):
        for item in store.BUILTIN_VARIABLES:
            self.assertTrue(item["name"])
            self.assertTrue(item["sample"])
            self.assertTrue(item["desc"])


class ProfileSummaryTest(unittest.TestCase):
    def test_summary_contains_address_tenant_user(self):
        doc = {
            "environments": {
                "生产": {
                    "base_url": "http://10.16.30.53",
                    "tenant": "财政一体化",
                    "username": "15500100111",
                }
            }
        }
        summary = store.profile_summary(doc, "生产")
        self.assertIn("http://10.16.30.53", summary)
        self.assertIn("财政一体化", summary)
        self.assertIn("15500100111", summary)


if __name__ == "__main__":
    unittest.main()


class CommandArgsTest(unittest.TestCase):
    """界面录制/回放命令拼装（纯函数，不需要真开窗口）。"""

    def test_record_args_with_menu(self):
        from ydf_recorder.gui import build_record_args

        args = build_record_args("生产", "/tmp/out.yaml", "项目库>>一级项目")
        self.assertEqual(
            args, ["--env", "生产", "--output", "/tmp/out.yaml", "--menu-path", "项目库>>一级项目"]
        )

    def test_record_args_without_menu(self):
        from ydf_recorder.gui import build_record_args

        self.assertEqual(
            build_record_args("测试", "/tmp/o.yaml"), ["--env", "测试", "--output", "/tmp/o.yaml"]
        )

    def test_replay_args_full(self):
        from ydf_recorder.gui import build_replay_args

        args = build_replay_args(
            "生产",
            "/tmp/a.yaml",
            {"files.预算表_xlsx": "/tmp/预算表.xlsx"},
            "/tmp/vars.yaml",
            headless=True,
        )
        self.assertEqual(args[:4], ["replay", "/tmp/a.yaml", "--env", "生产"])
        self.assertIn("--var", args)
        self.assertIn("files.预算表_xlsx=/tmp/预算表.xlsx", args)
        self.assertIn("--vars-file", args)
        self.assertIn("--headless", args)

    def test_replay_args_minimal(self):
        from ydf_recorder.gui import build_replay_args

        self.assertEqual(
            build_replay_args("测试", "/tmp/a.yaml"), ["replay", "/tmp/a.yaml", "--env", "测试"]
        )
