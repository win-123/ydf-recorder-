"""Windows 兼容性相关的单元测试（跨平台可跑，不依赖 Windows 本体）。

覆盖点：
- GUI 子进程的环境与 Popen 参数（UTF-8、隐藏控制台）
- 打包资源目录发现（Windows 布局：chromium / ydfbrowser-cli 与 exe 同级或上一层）
- 浏览器残留锁清理在 Windows 分支不去探测 pid（os.kill 在 Windows 会杀进程）
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

from ydf_recorder import gui, replay

DESKTOP = Path(__file__).resolve().parent.parent / "desktop"


def _load_desktop_entry():
    """desktop/entry.py 不在包内，按路径加载以便测试其纯函数。"""
    spec = importlib.util.spec_from_file_location("_ydf_desktop_entry", DESKTOP / "entry.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ChildProcessEnvTest(unittest.TestCase):
    def test_config_path_is_forwarded(self):
        env = gui.child_env("/tmp/env.yaml")
        self.assertEqual(env["YDF_RECORDER_CONFIG"], "/tmp/env.yaml")

    def test_stdio_is_pinned_to_utf8(self):
        # Windows 控制台默认 GBK：子进程必须显式 UTF-8，父进程才能按 UTF-8 解码
        env = gui.child_env("/tmp/env.yaml")
        self.assertEqual(env["PYTHONUTF8"], "1")
        self.assertEqual(env["PYTHONIOENCODING"], "utf-8")

    def test_popen_kwargs_empty_on_posix(self):
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertEqual(gui._child_popen_kwargs(), {})

    def test_popen_kwargs_hides_console_on_windows(self):
        with mock.patch.object(sys, "platform", "win32"):
            kwargs = gui._child_popen_kwargs()
        self.assertIn("creationflags", kwargs)
        self.assertNotEqual(kwargs["creationflags"], 0)


class FrozenBrowserPathTest(unittest.TestCase):
    """打包后内置 Chromium 的定位（Windows 布局回归）。"""

    def setUp(self):
        self.entry = _load_desktop_entry()
        self._env = mock.patch.dict("os.environ", {}, clear=False)
        self._env.start()
        import os

        os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)

    def tearDown(self):
        self._env.stop()

    def _run_with_layout(self, exe_path: Path, dirs: list[Path]) -> str | None:
        created = []
        try:
            for d in dirs:
                d.mkdir(parents=True, exist_ok=True)
                created.append(d)
            with mock.patch.object(self.entry.sys, "executable", str(exe_path)):
                self.entry._setup_bundled_browser()
            import os

            return os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        finally:
            import os

            for d in reversed(created):
                os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
                try:
                    d.rmdir()
                except OSError:
                    pass

    def test_windows_layout_chromium_beside_exe(self):
        import tempfile

        base = Path(tempfile.mkdtemp()) / "YonDiFRecorder"
        got = self._run_with_layout(base / "YonDiFRecorder.exe", [base / "chromium"])
        self.assertEqual(Path(got).resolve(), (base / "chromium").resolve())

    def test_chromium_one_level_up(self):
        import tempfile

        root = Path(tempfile.mkdtemp())
        app = root / "YonDiFRecorder"
        got = self._run_with_layout(app / "YonDiFRecorder.exe", [root / "chromium"])
        self.assertEqual(Path(got).resolve(), (root / "chromium").resolve())

    def test_no_chromium_leaves_env_untouched(self):
        import tempfile

        root = Path(tempfile.mkdtemp())
        got = self._run_with_layout(root / "YonDiFRecorder.exe", [])
        self.assertIsNone(got)


class ProfileLockTest(unittest.TestCase):
    """Windows 上不得用 os.kill 探测 pid（会真的终止进程）。"""

    def test_windows_never_probes_pid(self):
        import tempfile

        tmp = Path(tempfile.mkdtemp())
        lock = tmp / "SingletonLock"
        lock.write_text("host-123456", encoding="utf-8")
        with mock.patch.object(sys, "platform", "win32"), mock.patch.object(
            replay.os, "kill"
        ) as kill:
            self.assertFalse(replay._is_lock_owner_alive(lock))
        kill.assert_not_called()

    def test_windows_clears_plain_lock_files(self):
        import tempfile

        tmp = Path(tempfile.mkdtemp())
        for name in replay.LOCK_FILES:
            (tmp / name).write_text("x", encoding="utf-8")
        with mock.patch.object(sys, "platform", "win32"), mock.patch.object(
            replay, "_profile_dir", return_value=tmp
        ):
            replay._clear_stale_profile_lock()
        for name in replay.LOCK_FILES:
            self.assertFalse((tmp / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
