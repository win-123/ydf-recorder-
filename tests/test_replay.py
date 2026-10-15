"""内嵌 ydf-browser 回放运行时（replay.py）回归测试。

覆盖：
  - 源码目录发现（子模块 → 项目内 → 兄弟目录）
  - 运行时可执行文件发现的优先级（env > venv > PATH > interpreter）
  - run/validate 参数组装
  - JSON 摘要解析（ydf-browser _print_json 收尾格式）
  - 安装步骤生成
  - CLI 子命令接线
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ydf_recorder import replay  # noqa: E402
from ydf_recorder.cli import build_parser  # noqa: E402
from ydf_recorder.replay import (  # noqa: E402
    DiscoveryResult,
    ReplayOptions,
    build_install_steps,
    build_run_args,
    build_validate_args,
    default_config_path,
    discover_command,
    find_source_dir,
    parse_summary_json,
    runtime_python,
)


def make_source_dir(base: Path) -> Path:
    """构造一个合法的 ydf-browser 源码目录结构。"""
    pkg = base / "ydf_browser"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("__version__ = '0.0.0'\n")
    (base / "pyproject.toml").write_text("[project]\nname='ydf-browser'\n")
    return base


class TestFindSourceDir(unittest.TestCase):
    def test_vendor_submodule_found_first(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "recorder"
            root.mkdir()
            vendor = make_source_dir(root / "vendor" / "ydf-browser")
            make_source_dir(base / "ydf-browser")  # 兄弟目录也存在
            self.assertEqual(find_source_dir(root), vendor.resolve())

    def test_sibling_fallback(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "recorder"
            root.mkdir()
            sibling = make_source_dir(base / "ydf-browser")  # 位于临时目录内，不污染共享 T 目录
            self.assertEqual(find_source_dir(root), sibling.resolve())

    def test_none_when_missing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "recorder"
            root.mkdir()
            self.assertIsNone(find_source_dir(root))


class TestDiscoverCommand(unittest.TestCase):
    def test_env_override_python(self):
        result = discover_command(
            env={"YDF_BROWSER_BIN": "/opt/py/bin/python3.12"},
            which_fn=lambda _: None,
            importable_fn=lambda _: False,
        )
        self.assertTrue(result.found)
        self.assertEqual(result.command, ["/opt/py/bin/python3.12", "-m", "ydf_browser.cli"])
        self.assertEqual(result.source, "env:YDF_BROWSER_BIN")

    def test_env_override_console_script(self):
        result = discover_command(
            env={"YDF_BROWSER_BIN": "/usr/local/bin/ydf-browser"},
            which_fn=lambda _: None,
            importable_fn=lambda _: False,
        )
        self.assertEqual(result.command, ["/usr/local/bin/ydf-browser"])

    def test_runtime_venv_priority_over_path(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".ydf-browser-runtime" / "bin").mkdir(parents=True)
            venv_py = (root / ".ydf-browser-runtime" / "bin" / "python").resolve()
            venv_py.write_text("#!/bin/sh\n")
            result = discover_command(
                root=root,
                env={},
                which_fn=lambda _: "/should/not/win/ydf-browser",
                importable_fn=lambda _: True,
            )
            self.assertEqual(result.command, [str(venv_py), "-m", "ydf_browser.cli"])
            self.assertEqual(result.source, "runtime-venv")

    def test_path_fallback(self):
        result = discover_command(
            env={},
            which_fn=lambda name: f"/found/{name}" if name == "ydf-browser" else None,
            importable_fn=lambda _: False,
        )
        self.assertEqual(result.command, ["/found/ydf-browser"])
        self.assertEqual(result.source, "PATH")

    def test_interpreter_fallback(self):
        result = discover_command(
            env={},
            which_fn=lambda _: None,
            importable_fn=lambda name: name == "ydf_browser",
        )
        self.assertEqual(result.source, "interpreter")
        self.assertIn("-m", result.command or [])

    def test_not_found_hint_mentions_source_dir(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_source_dir(root / "vendor" / "ydf-browser")
            result = discover_command(
                root=root, env={}, which_fn=lambda _: None, importable_fn=lambda _: False,
            )
            self.assertFalse(result.found)
            self.assertIn("install-ydf-browser", result.hint)

    def test_not_found_hint_mentions_submodule(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "recorder"
            root.mkdir()
            result = discover_command(
                root=root, env={}, which_fn=lambda _: None, importable_fn=lambda _: False,
            )
            self.assertIn("git submodule add", result.hint)


class TestRuntimePython(unittest.TestCase):
    def test_runtime_python_found(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".ydf-browser-runtime" / "bin").mkdir(parents=True)
            py = root / ".ydf-browser-runtime" / "bin" / "python"
            py.write_text("")
            self.assertEqual(runtime_python(root), py.resolve())

    def test_runtime_python_missing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(runtime_python(Path(tmp)))


class TestDefaultConfigPath(unittest.TestCase):
    def test_returns_existing_config(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            cfg = root / "config" / "env.yaml"
            cfg.write_text("environments: {}\n")
            self.assertEqual(default_config_path(root), cfg.resolve())

    def test_none_when_missing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(default_config_path(Path(tmp)))


class TestBuildArgs(unittest.TestCase):
    def test_run_args_minimal(self):
        args = build_run_args(ReplayOptions(yaml_path="suite.yaml"))
        self.assertEqual(args, ["run", "suite.yaml", "--env", "ydf"])

    def test_run_args_full(self):
        opts = ReplayOptions(
            yaml_path="suite.yaml",
            env_name="prod",
            config="/cfg/env.yaml",
            headless=True,
            force_login=True,
            case_codes=["C1", "C2"],
            grep="预算",
            tags=["smoke"],
            vars_files=["v1.yaml"],
            no_persistent_profile=True,
        )
        args = build_run_args(opts)
        self.assertIn("--headless", args)
        self.assertIn("--force-login", args)
        self.assertIn("--no-persistent-profile", args)
        self.assertEqual(args[args.index("--case") + 1], "C1")
        self.assertEqual(args[args.index("--grep") + 1], "预算")
        self.assertEqual(args[args.index("--config") + 1], "/cfg/env.yaml")

    def test_run_args_no_config_when_none(self):
        args = build_run_args(ReplayOptions(yaml_path="a.yaml", config=None))
        self.assertNotIn("--config", args)

    def test_validate_args_exclude_browser_flags(self):
        args = build_validate_args(ReplayOptions(yaml_path="a.yaml", headless=True, force_login=True))
        self.assertEqual(args[0], "validate")
        self.assertNotIn("--headless", args)
        self.assertNotIn("--force-login", args)


class TestParseSummaryJson(unittest.TestCase):
    def test_last_json_line_wins(self):
        output = 'some log line\n{"a": 1}\nanother log\n{"success": true, "totals": {"cases": 3}}\n'
        summary = parse_summary_json(output)
        self.assertEqual(summary, {"success": True, "totals": {"cases": 3}})

    def test_none_when_no_json(self):
        self.assertIsNone(parse_summary_json("plain text\nonly logs\n"))

    def test_invalid_json_skipped(self):
        output = "{not valid json}\n{\"ok\": false}\n"
        self.assertEqual(parse_summary_json(output), {"ok": False})

    def test_ydf_browser_run_summary_shape(self):
        output = (
            "[progress] running case...\n"
            '{"success": false, "run_id": "r1", "totals": {"total": 1, "passed": 0, "failed": 1},'
            ' "report_file": "/tmp/report.json", "events_file": "/tmp/events.json",'
            ' "html_report_file": "/tmp/r.html",'
            ' "first_failure": {"case_code": "C1", "step_index": 3, "message": "元素未找到"}}\n'
        )
        summary = parse_summary_json(output)
        self.assertIsNotNone(summary)
        self.assertFalse(summary["success"])
        self.assertEqual(summary["first_failure"]["case_code"], "C1")


class TestBuildInstallSteps(unittest.TestCase):
    def test_steps_basic(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "ydf-browser"
            target = Path(tmp) / "runtime"
            steps = build_install_steps(src, target)
            self.assertEqual(len(steps), 3)
            self.assertIn("-m", steps[0])
            self.assertIn("venv", steps[0])
            self.assertIn(str(src), steps[1])
            self.assertIn("import ydf_browser", steps[-1][-1])

    def test_steps_with_browsers(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            steps = build_install_steps(Path(tmp) / "src", Path(tmp) / "rt", with_browsers=True)
            self.assertEqual(len(steps), 4)
            self.assertIn("install", steps[2])
            self.assertIn("chromium", steps[2])


class TestCliWiring(unittest.TestCase):
    def test_replay_subcommand_parses(self):
        parser = build_parser()
        args = parser.parse_args(["replay", "suite.yaml", "--headless", "--case", "C1"])
        self.assertEqual(args.command, "replay")
        self.assertEqual(args.yaml, "suite.yaml")
        self.assertTrue(args.headless)
        self.assertEqual(args.case, ["C1"])

    def test_validate_subcommand_has_no_headless(self):
        parser = build_parser()
        args = parser.parse_args(["validate", "suite.yaml"])
        self.assertEqual(args.command, "validate")
        self.assertFalse(hasattr(args, "headless"))

    def test_install_subcommand_parses(self):
        parser = build_parser()
        args = parser.parse_args(["install-ydf-browser", "--with-browsers"])
        self.assertEqual(args.command, "install-ydf-browser")
        self.assertTrue(args.with_browsers)
        self.assertIsNone(args.source)

    def test_record_still_default(self):
        parser = build_parser()
        args = parser.parse_args(["--env", "ydf"])
        self.assertNotEqual(args.command, "replay")

    def test_discovery_result_found_property(self):
        self.assertFalse(DiscoveryResult().found)
        self.assertTrue(DiscoveryResult(command=["x"]).found)


if __name__ == "__main__":
    unittest.main()
