"""登录页事件过滤回归测试。

登录由运行时根据 env 配置内置完成（ydf-browser DSL 无 login 动作），
登录页上的表单填写 / 点击不应进入业务用例：
  - converter.convert_events_to_steps 丢弃登录页事件（URL 含 login/cas、
    或标题「欢迎登录」），避免明文密码写进 YAML。
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ydf_recorder.models import (  # noqa: E402
    RecordedEvent,
    RecordedEventContext,
    RecordedEventTarget,
)
from ydf_recorder.converter import (  # noqa: E402
    _is_login_page_event,
    convert_events_to_steps,
)


def ev(etype: str, seq: int = 1, timestamp: int = 100,
       page_url: str = "", page_title: str = "", **target_kwargs) -> RecordedEvent:
    return RecordedEvent(
        type=etype,
        seq=seq,
        timestamp=timestamp,
        target=RecordedEventTarget(**target_kwargs),
        context=RecordedEventContext(url=page_url or "http://test",
                                     title=page_title or "测试"),
    )


def _login_fill_events() -> list[RecordedEvent]:
    """模拟登录页上的输入 + 点击（如 suite_20261029_080623 里的场景）。"""
    return [
        ev("input", seq=1, page_url="http://10.16.30.53/lightLogin",
           page_title="欢迎登录", label_text="邮箱/账号/用户手机号", value="15500100111"),
        ev("input", seq=2, page_url="http://10.16.30.53/lightLogin",
           page_title="欢迎登录", label_text="密码", value="secret123"),
        ev("click", seq=3, page_url="http://10.16.30.53/lightLogin",
           page_title="欢迎登录", text="登录"),
    ]


class TestIsLoginPageEvent(unittest.TestCase):
    """_is_login_page_event 判定。"""

    def test_url_contains_login(self):
        self.assertTrue(_is_login_page_event(
            ev("click", page_url="http://x/cas/login?xxx")))

    def test_url_contains_cas(self):
        self.assertTrue(_is_login_page_event(
            ev("click", page_url="http://x/cas/login_light")))

    def test_title_welcome_login(self):
        self.assertTrue(_is_login_page_event(
            ev("click", page_url="http://x/portal", page_title="欢迎登录")))

    def test_business_page_not_flagged(self):
        self.assertFalse(_is_login_page_event(
            ev("click", page_url="http://x/#/service/GX_PM3_SR",
               page_title="一级项目管理（财政）")))


class TestLoginEventsFilteredOut(unittest.TestCase):
    """登录页事件不得进入 YAML 步骤。"""

    def test_login_steps_dropped(self):
        events = _login_fill_events() + [
            ev("click", seq=10, page_url="http://x/#/service/GX_PM3_SR",
               page_title="一级项目管理（财政）",
               tag_name="span", region_type="top_action_bar", text="新增"),
        ]
        buf = io.StringIO()
        with redirect_stdout(buf):
            steps = convert_events_to_steps(events)
        labels = []
        for s in steps:
            target = s.get("target") or {}
            labels.extend((target.get("fields") or {}).keys())
            if target.get("label"):
                labels.append(target["label"])
        self.assertNotIn("邮箱/账号/用户手机号", labels)
        self.assertNotIn("密码", labels)
        self.assertNotIn("登录", labels)
        # 业务步骤保留
        self.assertIn("新增", labels)
        # 提示输出
        self.assertIn("登录页", buf.getvalue())

    def test_clean_recording_untouched(self):
        events = [
            ev("click", seq=1, page_url="http://x/#/service/GX_PM3_SR",
               page_title="一级项目管理（财政）",
               tag_name="span", region_type="top_action_bar", text="新增"),
            ev("click", seq=2, page_url="http://x/#/service/GX_PM3_SR",
               page_title="一级项目管理（财政）",
               tag_name="span", region_type="top_action_bar", text="保存"),
        ]
        steps = convert_events_to_steps(events)
        self.assertEqual(len(steps), 2)


class TestPreServiceNoiseDropped(unittest.TestCase):
    """带 open_menu 时，到达业务页（/service/）之前的导航噪音应被丢弃。"""

    def test_portal_clicks_dropped_when_open_menu(self):
        events = [
            # 门户页（财政一体化）点菜单 —— 导航噪音
            ev("click", seq=1, page_url="http://x/", page_title="财政一体化",
               tag_name="span", text="一级项目管理（财政）"),
            # 业务页事件
            ev("click", seq=5, page_url="http://x/#/service/GX_PM3_SR",
               page_title="一级项目管理（财政）",
               tag_name="span", region_type="top_action_bar", text="新增"),
        ]
        buf = io.StringIO()
        with redirect_stdout(buf):
            steps = convert_events_to_steps(events, has_open_menu=True)
        labels = [str((s.get("target") or {}).get("label")) for s in steps]
        self.assertNotIn("一级项目管理（财政）", labels)
        self.assertIn("新增", labels)
        self.assertIn("导航", buf.getvalue())

    def test_portal_clicks_kept_without_open_menu(self):
        events = [
            ev("click", seq=1, page_url="http://x/", page_title="财政一体化",
               tag_name="span", text="一级项目管理（财政）"),
        ]
        steps = convert_events_to_steps(events, has_open_menu=False)
        self.assertEqual(len(steps), 1)

    def test_all_non_service_urls_kept(self):
        """整个事件流都不含 /service/ 时保守保留全部。"""
        events = [
            ev("click", seq=1, page_url="http://x/portal", page_title="门户",
               tag_name="span", text="某按钮"),
        ]
        steps = convert_events_to_steps(events, has_open_menu=True)
        self.assertEqual(len(steps), 1)


if __name__ == "__main__":
    unittest.main()
