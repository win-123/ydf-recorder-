"""
录制器运行时（Playwright codegen 风格）。

架构：
  - 目标窗口：打开目标环境，**只注入隐形的 RECORDER_JS** 捕获事件，页面保持干净
    （不再贴浮动面板，避免遮挡页面）。
  - 检查器窗口：**单独的浏览器窗口**，承担控制台（Stop / Pause / 解除遮挡 / 复制）
    与**实时 YAML 预览**。
  - Python 运行时：在 ``wait_for_stop`` 轮询中，从目标窗口拉取已捕获事件，
    用 ``converter.py`` 转成 YAML，推送到检查器窗口实时显示；检查器按钮通过
    ``expose_function`` 回调 Python，再操作目标窗口。

事件持久化在 sessionStorage（见 RECORDER_JS），整页跳转后 ``_ensure_installed``
会重新注入并恢复历史事件，录制连续不中断。
"""

from __future__ import annotations

import json
import time
from typing import Any

from .config import RecorderEnv
from .converter import build_dsl_document, dsl_to_yaml
from .inject import RECORDER_JS
from .menu_resolver import resolve_menu_path_from_tree
from .models import RecordedEvent, RecordingSession

# 解除目标页遮挡：剥离覆盖大部分视窗的 fixed/absolute 遮罩层（Cookie/隐私/登录弹窗及其 backdrop）。
# 由检查器窗口的「解除遮挡」按钮触发（经 Python 在目标窗口上执行）。
UNBLOCK_JS = r"""
window.__ydf_recorder_unblock = function () {
  var removed = [];
  var vw = window.innerWidth, vh = window.innerHeight;
  var LAYOUT_KW = /^(um-win|portal-workbench|wx-root|wx-\d|diwork|content--|menuBarPart|top-bg|layout-item)/;
  function isRecorderEl(el) {
    var p = el;
    while (p) {
      if (p.id && String(p.id).indexOf('__ydf_recorder') === 0) return true;
      p = p.parentElement;
    }
    return false;
  }
  function peel(doc) {
    try {
      var els = doc.querySelectorAll('div, section, aside');
      for (var i = 0; i < els.length; i++) {
        var el = els[i];
        if (isRecorderEl(el)) continue;
        var cs = (doc.defaultView || window).getComputedStyle(el);
        if (cs.position !== 'fixed' && cs.position !== 'absolute' && cs.position !== 'sticky') continue;
        if (cs.display === 'none' || cs.visibility === 'hidden') continue;
        var r = el.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) continue;
        if ((r.width * r.height) / (vw * vh) < 0.4) continue;
        var cls = (typeof el.className === 'string' ? el.className : '');
        if (LAYOUT_KW.test(cls)) continue;
        removed.push(el.id ? ('#' + el.id) : (cls ? '.' + cls.split(/\s+/)[0] : el.tagName));
        el.style.setProperty('display', 'none', 'important');
      }
    } catch (e) {}
  }
  peel(document);
  var iframes = document.querySelectorAll('iframe');
  for (var j = 0; j < iframes.length; j++) {
    try { peel(iframes[j].contentDocument); } catch (e) {}
  }
  try { console.log('[ydf-recorder] unblock removed', removed.length, removed.slice(0, 10)); } catch (e) {}
  return removed;
};
"""

# 精准清除 Cookie/隐私同意横幅：只删「文本含隐私/Cookie/consent 等关键词」的大面积遮罩，
# 避免误伤业务弹窗与登录表单（如 CAS 登录 body）。由录制器周期性跨 frame 调用，
# 以抓住异步渲染的同意框。
COOKIE_DISMISS_JS = r"""
window.__ydf_recorder_dismiss = function () {
  var removed = [];
  var vw = window.innerWidth, vh = window.innerHeight;
  var KW = /隐私|cookie|Cookie|COOKIE|consent|Consent|使用Cookie|隐私政策|我们使用|个性化|personaliz|GDPR|Do Not Sell|同意.{0,6}Cookie|接受.{0,4}Cookie/i;
  function isRec(el) { var p = el; while (p) { if (p.id && String(p.id).indexOf('__ydf_recorder') === 0) return true; p = p.parentElement; } return false; }
  try {
    var els = document.querySelectorAll('div, aside, section');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (isRec(el)) continue;
      var cs = (document.defaultView || window).getComputedStyle(el);
      if (cs.position !== 'fixed' && cs.position !== 'absolute' && cs.position !== 'sticky') continue;
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      var r = el.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) continue;
      if ((r.width * r.height) / (vw * vh) < 0.15) continue;
      var txt = (el.textContent || '').slice(0, 300);
      if (!KW.test(txt)) continue;
      removed.push((el.id ? '#' + el.id : '.') + (typeof el.className === 'string' ? el.className.split(/\s+/)[0] : ''));
      el.style.setProperty('display', 'none', 'important');
    }
  } catch (e) {}
  return removed;
};
"""

# 检查器窗口内容：控制台 + 实时 YAML 预览。set_content 注入，<script> 可正常执行。
INSPECTOR_HTML = r"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>ydf-browser Recorder</title>
<style>
  * { box-sizing: border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:#0f0f1a; color:#eee; display:flex; flex-direction:column; height:100vh; }
  header { padding:10px 14px; background:#1a1a2e; border-bottom:1px solid #2a2a44; display:flex; align-items:center; gap:8px; }
  .dot { width:9px; height:9px; border-radius:50%; background:#f44336; animation:ydf-blink 1s infinite; flex:0 0 auto; }
  .dot.paused { background:#ff9800; animation:none; }
  h1 { font-size:13px; margin:0; font-weight:700; color:#4fc3f7; }
  .count { margin-left:auto; font-size:12px; color:#888; flex:0 0 auto; }
  .count b { color:#fff; font-size:15px; font-variant-numeric:tabular-nums; }
  .bar { padding:8px 12px; background:#15152a; border-bottom:1px solid #2a2a44; display:flex; gap:6px; flex-wrap:wrap; }
  button { padding:6px 12px; border:none; border-radius:5px; cursor:pointer; font-size:12px; font-weight:600; }
  button:active { transform: translateY(1px); }
  .stop { background:#f44336; color:#fff; }
  .pause { background:#ff9800; color:#000; }
  .unblock { background:#2d2d44; color:#bbb; border:1px solid #3a3a55; }
  .copy { background:#4caf50; color:#fff; }
  .hint { padding:6px 12px; font-size:11px; color:#666; background:#0f0f1a; border-bottom:1px solid #1a1a2e; }
  pre { margin:0; padding:12px; flex:1; overflow:auto; font-family:ui-monospace,Menlo,Consolas,monospace; font-size:12px; line-height:1.55; white-space:pre; color:#9cffb0; }
  .toast { position:fixed; bottom:10px; left:50%; transform:translateX(-50%); background:#333; color:#fff; padding:5px 12px; border-radius:5px; font-size:12px; opacity:0; transition:opacity .2s; pointer-events:none; }
  .toast.show { opacity:1; }
  .paused-banner { display:none; padding:4px 12px; background:#ff9800; color:#000; font-size:12px; font-weight:600; text-align:center; }
  .paused-banner.show { display:block; }
  @keyframes ydf-blink { 0%,100%{opacity:1} 50%{opacity:0.3} }
</style>
</head>
<body>
<header>
  <span class="dot" id="dot"></span>
  <h1>ydf-browser Recorder</h1>
  <span class="count"><b id="count">0</b> events · 实时 YAML</span>
</header>
<div class="bar">
  <button class="stop" id="stop">■ Stop Recording</button>
  <button class="pause" id="pause">⏸ Pause</button>
  <button class="unblock" id="unblock">解除目标页遮挡</button>
  <button class="copy" id="copy">复制 YAML</button>
</div>
<div class="hint" id="hint-recording">在另一个窗口的目标页操作，这里实时生成 YAML。点 Stop 结束并写入文件。</div>
<div class="paused-banner" id="paused-banner">⏸ 录制已暂停 — 点击 Resume 继续</div>
<pre id="yaml"># 启动中…</pre>
<div class="toast" id="toast"></div>
<script>
  var paused = false;
  function toast(msg) {
    var t = document.getElementById('toast');
    t.textContent = msg; t.classList.add('show');
    setTimeout(function () { t.classList.remove('show'); }, 1500);
  }
  function applyPausedState(p) {
    paused = p;
    document.getElementById('pause').textContent = p ? '▶ Resume' : '⏸ Pause';
    document.getElementById('dot').classList.toggle('paused', p);
    document.getElementById('paused-banner').classList.toggle('show', p);
  }
  window.__ydf_render = function (yaml, count) {
    var el = document.getElementById('yaml');
    el.textContent = yaml || '(暂无步骤)';
    document.getElementById('count').textContent = String(count);
    el.scrollTop = el.scrollHeight;
  };
  window.__ydf_set_paused = function (p) {
    applyPausedState(p);
  };
  window.__ydf_unblock_done = function (n) {
    toast('已移除 ' + n + ' 个遮挡');
  };
  document.getElementById('stop').addEventListener('click', function () {
    if (window.__ydf_stop) window.__ydf_stop();
  });
  document.getElementById('pause').addEventListener('click', function () {
    // ★ 乐观更新：立即切换 UI 状态，不等 Python 回调
    var newState = !paused;
    applyPausedState(newState);
    var p = newState ? (window.__ydf_pause ? window.__ydf_pause() : null)
                     : (window.__ydf_resume ? window.__ydf_resume() : null);
    if (p && typeof p.catch === 'function') {
      p.then(function() { toast(newState ? '已暂停录制' : '已恢复录制'); },
             function() { applyPausedState(!newState); toast('操作失败，请重试'); });
    } else {
      toast(newState ? '已暂停录制' : '已恢复录制');
    }
  });
  document.getElementById('unblock').addEventListener('click', function () {
    if (window.__ydf_unblock) window.__ydf_unblock();
  });
  document.getElementById('copy').addEventListener('click', function () {
    var text = document.getElementById('yaml').textContent;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function(){toast('已复制');}, function(){fallbackCopy(text);});
      } else { fallbackCopy(text); }
    } catch (e) { fallbackCopy(text); }
  });
  function fallbackCopy(text) {
    try {
      var ta = document.createElement('textarea');
      ta.value = text; document.body.appendChild(ta); ta.select();
      document.execCommand('copy'); document.body.removeChild(ta); toast('已复制');
    } catch (e) { toast('复制失败'); }
  }
</script>
</body>
</html>
"""


class RecorderRuntime:
    """录制器 Playwright 运行时（codegen 风格：目标窗口 + 独立检查器窗口）。

    目标窗口注入 RECORDER_JS 捕获事件；检查器窗口显示控制台与实时 YAML。
    """

    def __init__(
        self,
        config: RecorderEnv,
        *,
        menu_path: str = "",
        auto_login: bool = True,
    ) -> None:
        self.config = config
        self._menu_path = menu_path.strip() if menu_path else ""
        self._auto_login = auto_login
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None  # 目标页
        self._inspector_ctx = None
        self._inspector = None  # 检查器窗口
        self._headless = False  # 录制必须 headed
        self._stopped = False
        self._paused = False
        self._events: list[dict[str, Any]] = []
        self._poll_interval_ms = 500
        self._service_code: str = ""  # 菜单解析得到的 serviceCode
        self._api_session = None  # requests.Session for API calls (aligned with ydf-browser)

    # ── 启动 ──────────────────────────────────────────────────

    def start(self) -> None:
        """启动浏览器：登录 → 打开菜单 → 注入捕获脚本 → 另开检查器窗口。

        如果配置了用户名/密码且 ``auto_login=True``，会自动执行 CAS 登录并
        注入 cookies；如果配置了 ``menu_path``，会解析菜单树并导航到目标
        服务页面。登录或菜单打开失败时降级为手动模式（仅打开 base_url）。
        """
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=False,
            args=["--window-size=1440,900", "--window-position=0,0"],
        )

        # 目标窗口
        self._context = self._browser.new_context(
            locale="zh-CN",
            accept_downloads=True,
            viewport={"width": 1440, "height": 900},
        )
        # ★ 设置默认超时，防止页面加载中 evaluate 长时间阻塞
        self._context.set_default_timeout(10000)
        self._page = self._context.new_page()
        self._page.on("frameattached", self._on_frame_attached)

        # ── 环境准备：登录 + 打开菜单 ──
        self._prepare_environment()

        self._inject_recorder()
        # 启动后精准清除 Cookie/隐私横幅（不伤登录表单）
        self._dismiss_cookie_all_frames()

        # 检查器窗口（独立 context = 独立 OS 窗口）
        self._inspector_ctx = self._browser.new_context(
            viewport={"width": 560, "height": 900}
        )
        self._inspector = self._inspector_ctx.new_page()

        # ★ 通过 CDP 把检查器窗口定位到屏幕右侧，避免遮挡目标窗口
        self._position_inspector_right()

        # expose_function 必须在脚本调用前注册；检查器按钮在用户点击时才调用
        self._inspector.expose_function("__ydf_stop", self._on_stop)
        self._inspector.expose_function("__ydf_pause", self._on_pause)
        self._inspector.expose_function("__ydf_resume", self._on_resume)
        self._inspector.expose_function("__ydf_unblock", self._on_unblock)
        self._inspector.set_content(INSPECTOR_HTML)
        # ★ 确保 __ydf_render 已定义再进入轮询，避免首次推送被静默丢弃
        try:
            self._inspector.wait_for_function(
                "() => typeof window.__ydf_render === 'function'", timeout=5000
            )
        except Exception as ex:
            print(f"[ydf-recorder] ⚠️ inspector __ydf_render not ready: {ex}", flush=True)
        try:
            self._inspector.set_default_timeout(10000)
        except Exception:
            pass
        try:
            # 目标窗口置于最前，检查器在侧边不遮挡
            self._page.bring_to_front()
        except Exception:
            pass

    # ── 环境准备：登录 + 打开菜单 ──────────────────────────────

    def _prepare_environment(self) -> None:
        """登录并导航到目标菜单（如果配置了），失败时降级为手动模式。"""
        login_ok = False
        if self._auto_login and self.config.username and self.config.password:
            try:
                self._do_login()
                login_ok = True
            except Exception as exc:
                print(
                    f"[ydf-recorder] ⚠️ 自动登录失败: {exc}，降级为手动登录",
                    flush=True,
                )

        if not login_ok:
            self._page.goto(self.config.base_url, wait_until="domcontentloaded")

        if self._menu_path:
            try:
                self._open_menu()
            except Exception as exc:
                print(
                    f"[ydf-recorder] ⚠️ 打开菜单失败: {exc}，请手动导航到目标页面",
                    flush=True,
                )

    def _do_login(self) -> None:
        """执行 CAS 登录，将 session cookies 注入 Playwright 浏览器上下文。

        流程：
          1. ``auth.login(env)`` — RSA 加密 + POST 表单 + 跟随重定向
          2. **立即注入 cookies 到浏览器** — 确保后续请求都携带登录态
          3. ``auth.apply_context(...)`` — 切换租户/组织/业务年度（按需）
             失败时仅警告，不阻断（cookies 已注入，用户仍可手动操作）
          4. 导航到 base_url
        """
        from .auth import apply_context, cookies_for_playwright, login

        print(
            f"[ydf-recorder] 正在登录 {self.config.base_url} "
            f"(user={self.config.username})…",
            flush=True,
        )
        result = login(self.config)
        self._api_session = result.session  # save session for _open_menu

        # ★ 关键：先注入 cookies，再尝试上下文切换
        # 这样即使上下文切换失败，浏览器仍处于登录状态
        cookies = cookies_for_playwright(self.config, result.session)
        if cookies:
            self._context.add_cookies(cookies)
            print(
                f"[ydf-recorder] 已注入 {len(cookies)} 个登录 cookies",
                flush=True,
            )

        # 上下文切换（租户/组织/业务年度），仅在配置了对应值时执行
        # 失败时仅警告，不抛异常 — cookies 已注入，菜单打开仍可能成功
        tenant = self.config.tenant
        default_org = self.config.default_org
        fiscal_year = self.config.fiscal_year
        if tenant or default_org or fiscal_year:
            print(
                f"[ydf-recorder] 切换上下文: tenant={tenant or '(跳过)'}, "
                f"org={default_org or '(跳过)'}, fiscal_year={fiscal_year or '(跳过)'}",
                flush=True,
            )
            try:
                result = apply_context(
                    self.config,
                    result,
                    tenant_name=tenant,
                    default_org=default_org,
                    fiscal_year=fiscal_year,
                )
                # 上下文切换后 session 已更新（重新登录），清除旧 cookie 再注入新的
                self._api_session = result.session  # update session
                cookies2 = cookies_for_playwright(self.config, result.session)
                if cookies2:
                    self._context.clear_cookies()
                    self._context.add_cookies(cookies2)
                    print(
                        f"[ydf-recorder] 上下文切换后重新注入 {len(cookies2)} 个 cookies",
                        flush=True,
                    )
            except Exception as exc:
                print(
                    f"[ydf-recorder] ⚠️ 上下文切换失败: {exc}（cookies 已注入，继续）",
                    flush=True,
                )

        # 导航到首页
        self._page.goto(self.config.base_url, wait_until="domcontentloaded")
        print("[ydf-recorder] 登录完成", flush=True)

    def _open_menu(self) -> None:
        """通过菜单树解析 serviceCode 并导航到对应服务页面。

        使用 ``requests.Session``（与 ydf-browser 对齐）拉取菜单树，
        确保携带正确的登录态 cookies。再用 ``menu.resolve_menu_to_service_code``
        正向解析中文路径 -> serviceCode，最后导航到 ``/#/service/{serviceCode}``。
        """
        from .menu import build_service_url, resolve_menu_to_service_code
        from .menu_resolver import _walk_menu_tree
        from .menu import _unwrap_payload
        from urllib.parse import urljoin

        print(f"[ydf-recorder] 正在打开菜单: {self._menu_path}", flush=True)

        # 用 requests.Session 拉取菜单树（与 ydf-browser gateway.resolve_menu 一致）
        if self._api_session is None:
            raise RuntimeError("未登录，无法拉取菜单树")
        url = urljoin(self.config.base_url, self.config.endpoints.service_tree)
        response = self._api_session.get(url, timeout=20)
        if not response.ok:
            raise RuntimeError(f"拉取菜单树失败: HTTP {response.status_code}")
        try:
            payload = response.json()
        except Exception:
            body = response.text[:200]
            raise RuntimeError(
                f"菜单树接口返回非 JSON（可能未登录），响应前200字符: {body}"
            )

        # 调试：dump 菜单树 + 打印所有路径
        import os as _os, tempfile as _tf
        _dp = _os.path.join(_tf.gettempdir(), "ydf_menu_tree_debug.json")
        try:
            with open(_dp, "w", encoding="utf-8") as _f:
                json.dump(payload, _f, ensure_ascii=False, indent=2)
            print(f"[ydf-recorder] 菜单树已 dump: {_dp}", flush=True)
        except Exception:
            pass
        _tree = _unwrap_payload(payload)
        _all_paths = [">>".join(_p) for _, _p in _walk_menu_tree(_tree, [])]
        print(f"[ydf-recorder] 菜单树共 {len(_all_paths)} 个节点", flush=True)
        for _i, _p in enumerate(_all_paths[:30]):
            print(f"  [{_i}] {_p}", flush=True)
        _path_parts = [part.strip() for part in self._menu_path.split(">>") if part.strip()]
        if _path_parts:
            _fuzzy = [_p for _p in _all_paths if any(part in _p for part in _path_parts)]
            if _fuzzy:
                print(f"[ydf-recorder] 模糊匹配到的路径:", flush=True)
                for _p in _fuzzy[:20]:
                    print(f"  -> {_p}", flush=True)

        service_code = resolve_menu_to_service_code(payload, self._menu_path)
        self._service_code = service_code
        service_url = build_service_url(self.config.base_url, service_code)
        print(
            f"[ydf-recorder] 菜单解析: {self._menu_path} -> "
            f"serviceCode={service_code}",
            flush=True,
        )

        # ★ 与 ydf-browser 对齐：打开菜单前重新注入最新 cookies，
        # 避免首页导航后 cookies 过期/被服务端刷新导致服务页跳回登录
        from .auth import cookies_for_playwright
        if self._api_session is not None:
            fresh_cookies = cookies_for_playwright(self.config, self._api_session)
            if fresh_cookies:
                try:
                    self._context.clear_cookies()
                    self._context.add_cookies(fresh_cookies)
                except Exception:
                    pass

        # ★ 与 ydf-browser 对齐：如果当前已在同域（如首页），开新标签页打开服务页，
        # 给 SPA 一个干净的页面状态
        current_url = self._page.url or ""
        base_host = service_url.split("#", 1)[0].rstrip("/")
        if current_url.rstrip("/") == base_host and "#" in service_url:
            try:
                new_page = self._context.new_page()
                new_page.goto(service_url, wait_until="domcontentloaded")
                self._page.close()
                self._page = new_page
                self._page.on("frameattached", self._on_frame_attached)
            except Exception:
                self._page.goto(service_url, wait_until="domcontentloaded")
        else:
            self._page.goto(service_url, wait_until="domcontentloaded")

        # 等待页面网络空闲（超时不致命，SPA 可能持续轮询）
        try:
            self._page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        print(f"[ydf-recorder] 已打开菜单页面: {service_url}", flush=True)

    def _on_frame_attached(self, frame) -> None:
        """动态 frame 创建时注入录制器。"""
        try:
            frame.evaluate(RECORDER_JS)
        except Exception:
            pass

    def _inject_recorder(self) -> None:
        """向目标页所有 frame 注入录制器 JS。"""
        for frame in self._page.frames:
            try:
                frame.evaluate(RECORDER_JS)
            except Exception:
                pass

    def _position_inspector_right(self) -> None:
        """通过 CDP 把检查器窗口移动到屏幕右侧，避免遮挡目标录制窗口。

        目标窗口固定在左侧 (0,0) 宽 1440；检查器窗口放到 1450 处靠右。
        若屏幕宽度不够则贴右边缘显示。
        """
        inspector_w = 560
        target_w = 1440
        gap = 10
        try:
            # 从目标页获取屏幕尺寸
            screen_info = self._page.evaluate(
                "() => ({w: screen.width, h: screen.height})"
            )
            screen_w = screen_info.get("w", 1920)
            screen_h = screen_info.get("h", 1080)
        except Exception:
            screen_w, screen_h = 1920, 1080

        # 理想位置：紧挨目标窗口右侧
        ideal_left = target_w + gap
        # 如果屏幕放不下（目标+检查器 > 屏幕宽），检查器贴右边缘
        if ideal_left + inspector_w > screen_w:
            ideal_left = max(0, screen_w - inspector_w)

        try:
            cdp = self._inspector_ctx.new_cdp_session(self._inspector)
            # 获取检查器窗口 ID
            result = cdp.send("Browser.getWindowForTarget")
            window_id = result.get("windowId")
            if window_id is not None:
                cdp.send("Browser.setWindowBounds", {
                    "windowId": window_id,
                    "bounds": {
                        "left": ideal_left,
                        "top": 0,
                        "width": inspector_w,
                        "height": screen_h,
                        "windowState": "normal",
                    },
                })
                print(
                    f"[ydf-recorder] 检查器窗口已定位到右侧 "
                    f"(left={ideal_left}, top=0, {inspector_w}x{screen_h})",
                    flush=True,
                )
        except Exception as ex:
            print(f"[ydf-recorder] ⚠️ 定位检查器窗口失败: {ex}", flush=True)

    def _ensure_installed(self) -> None:
        """整页跳转后录制脚本会被冲掉；每轮轮询前确认仍在，缺失则重新注入。

        事件持久化在 sessionStorage，重新注入后自动恢复，录制连续不中断。
        若此前处于暂停态，重新注入后重新置为暂停。
        """
        try:
            installed = self._page.evaluate("() => !!window.__ydf_recorder_installed")
        except Exception:
            installed = False
        if not installed:
            self._inject_recorder()
            if self._paused:
                self._pause_target()
            # 跳转后页面重新加载，再次精准清除 Cookie/隐私横幅
            self._dismiss_cookie_all_frames()

    # ── 检查器回调（由检查器窗口按钮触发）─────────────────────

    def _on_stop(self) -> None:
        self._stopped = True

    def _on_pause(self) -> None:
        self._paused = True
        self._pause_target()
        self._set_inspector_paused(True)

    def _on_resume(self) -> None:
        self._paused = False
        try:
            self._page.evaluate("() => window.__ydf_recorder_resume && window.__ydf_recorder_resume()")
        except Exception:
            pass
        self._set_inspector_paused(False)

    def _unblock_all_frames(self) -> tuple[int, list[str]]:
        """在目标页所有 frame（含跨域 iframe）执行解除遮挡，返回 (总数, 明细)。"""
        total = 0
        details: list[str] = []
        for frame in self._page.frames:
            url = frame.url or "(blank)"
            try:
                frame.evaluate(UNBLOCK_JS)
                removed = frame.evaluate(
                    "() => (window.__ydf_recorder_unblock ? window.__ydf_recorder_unblock() : [])"
                ) or []
            except Exception:
                removed = []
            if removed:
                total += len(removed)
                details.append(f"{url[:48]} → {list(removed)[:3]}")
        return total, details

    def _dismiss_cookie_all_frames(self) -> int:
        """跨 frame 精准清除 Cookie/隐私横幅（文本关键词匹配，不伤业务弹窗/登录表单）。"""
        total = 0
        for frame in self._page.frames:
            try:
                frame.evaluate(COOKIE_DISMISS_JS)
                removed = frame.evaluate(
                    "() => (window.__ydf_recorder_dismiss ? window.__ydf_recorder_dismiss() : [])"
                ) or []
            except Exception:
                removed = []
            if removed:
                total += len(removed)
                print(
                    f"[ydf-recorder] dismissed cookie overlay in {frame.url[:48]}: {list(removed)[:5]}",
                    flush=True,
                )
        return total

    def _diagnose_overlays(self) -> list[str]:
        """扫描所有 frame 里真正可能拦截点击的遮罩元素（排除布局容器）。

        优化点：
        - 用轻量选择器替代 querySelectorAll('*')，只扫描 div/section/aside
        - 排除已知布局容器（um-win, portal-workbench, wx-root, diwork, content-- 等）
        - 只报告 pointer-events 不为 none 且 z-index 较高的元素
        """
        findings: list[str] = []
        for frame in self._page.frames:
            try:
                res = frame.evaluate(
                    r"""() => {
                      var vw = window.innerWidth, vh = window.innerHeight, out = [];
                      // 已知布局容器类名关键词——这些是页面框架的正常容器，不是遮挡层
                      var LAYOUT_KW = /^(um-win|portal-workbench|wx-root|wx-\d|diwork|content--|menuBarPart|top-bg|layout-item|ant-spin|ant-modal-wrap|ant-drawer-mask)/;
                      try {
                        var els = document.querySelectorAll('div, section, aside');
                        for (var i = 0; i < els.length; i++) {
                          var el = els[i];
                          if (el.id && String(el.id).indexOf('__ydf_recorder') === 0) continue;
                          var cs = (document.defaultView || window).getComputedStyle(el);
                          if (cs.position !== 'fixed' && cs.position !== 'absolute' && cs.position !== 'sticky') continue;
                          if (cs.display === 'none' || cs.visibility === 'hidden') continue;
                          // 跳过 pointer-events:none 的元素——它们不会拦截点击
                          if (cs.pointerEvents === 'none') continue;
                          var r = el.getBoundingClientRect();
                          if (r.width <= 0 || r.height <= 0) continue;
                          var cov = (r.width * r.height) / (vw * vh);
                          if (cov < 0.25) continue;
                          var cls = (typeof el.className === 'string' ? el.className : '');
                          // 排除已知布局容器
                          if (LAYOUT_KW.test(cls)) continue;
                          // 排除 helper iframe 容器
                          if (cls.indexOf('yondif-ai-adapter') >= 0) continue;
                          var txt = (el.textContent || '').replace(/\s+/g, ' ').slice(0, 50);
                          out.push({
                            tag: el.tagName,
                            id: el.id || '',
                            cls: cls.slice(0, 40),
                            cov: Math.round(cov * 100),
                            z: cs.zIndex,
                            pe: cs.pointerEvents,
                            txt: txt
                          });
                        }
                      } catch (e) {}
                      return out.slice(0, 10);
                    }"""
                ) or []
            except Exception:
                res = []
            for it in res:
                findings.append(
                    f"[{frame.url[:32]}] <{it.get('tag')}> id={it.get('id')!r} "
                    f"cls={it.get('cls')!r} cov={it.get('cov')}% z={it.get('z')} "
                    f"pe={it.get('pe')} txt={it.get('txt')!r}"
                )
        return findings

    def _on_unblock(self) -> int:
        """检查器「解除遮挡」按钮：跨 frame 解除并把数量回报检查器。"""
        total, details = self._unblock_all_frames()
        try:
            self._inspector.evaluate(
                "(n) => { if (window.__ydf_unblock_done) window.__ydf_unblock_done(n); }", total
            )
        except Exception:
            pass
        print(
            f"[ydf-recorder] unblock: removed {total}; details: {details}",
            flush=True,
        )
        return total

    def _pause_target(self) -> None:
        try:
            self._page.evaluate("() => window.__ydf_recorder_pause && window.__ydf_recorder_pause()")
        except Exception:
            pass

    def _set_inspector_paused(self, paused: bool) -> None:
        try:
            self._inspector.evaluate("(p) => { if (window.__ydf_set_paused) window.__ydf_set_paused(p); }", paused)
        except Exception:
            pass

    # ── 事件采集与实时 YAML ───────────────────────────────────

    def _capture_events(self) -> list[dict[str, Any]]:
        """从目标页拉取当前已捕获的全部事件。"""
        try:
            result = self._page.evaluate(
                "JSON.stringify(window.__ydf_recorder_dump ? window.__ydf_recorder_dump() : [])"
            )
            data = json.loads(result) if isinstance(result, str) else result
            return data or []
        except Exception as ex:
            print(f"[ydf-recorder] ⚠️ _capture_events error: {ex}", flush=True)
            return []

    def _live_yaml(self, raw_events: list[dict[str, Any]]) -> str:
        """用 converter 把当前事件列表转成 YAML，供检查器实时预览。"""
        if not raw_events:
            return "# 暂无步骤——在目标页操作，这里会实时生成 YAML"
        try:
            events = [RecordedEvent.from_dict(e) for e in raw_events]
        except Exception:
            return "# 事件解析中…"
        title = "录制预览"
        for e in events:
            if e.context.title:
                title = e.context.title
        session = RecordingSession(
            suite_code="recorded_suite",
            suite_name=title,
            tenant=self.config.tenant,
            default_org=self.config.default_org,
            user=self.config.default_user,
            events=events,
        )
        try:
            document = build_dsl_document(session)
            return dsl_to_yaml(document)
        except Exception as ex:
            return f"# 转换出错: {ex}"

    def _push_to_inspector(self, yaml_text: str, count: int) -> None:
        try:
            # ★ Playwright evaluate 只接受一个 arg 参数，必须把 yaml + count 合并为单个列表
            self._inspector.evaluate(
                "([y, c]) => { window.__ydf_render(y, c); }",
                [yaml_text, count],
            )
        except Exception as ex:
            if not hasattr(self, '_push_warned'):
                self._push_warned = True
                print(f"[ydf-recorder] ⚠️ _push_to_inspector error: {ex}", flush=True)

    # ── 主循环 ────────────────────────────────────────────────

    def wait_for_stop(self) -> list[dict[str, Any]]:
        """轮询目标页事件、实时推送 YAML 到检查器，直到用户在检查器点 Stop。"""
        print(
            "[ydf-recorder] Recording started. Operate the target page; "
            "watch the inspector window for live YAML. Click 'Stop Recording' to finish.",
            flush=True,
        )

        last_diag = 0.0
        last_dismiss = 0.0
        poll_count = 0
        while not self._stopped:
            try:
                self._ensure_installed()
                # ★ 优先推送 YAML 到检查器，确保实时预览不被低优先级任务阻塞
                raw_events = self._capture_events()
                yaml_text = self._live_yaml(raw_events)
                self._push_to_inspector(yaml_text, len(raw_events))
                poll_count += 1
                if poll_count <= 3:
                    print(
                        f"[ydf-recorder] poll #{poll_count}: {len(raw_events)} events, "
                        f"yaml={len(yaml_text)} chars",
                        flush=True,
                    )
                now = time.monotonic()
                if not self._paused:
                    # ★ 暂停时跳过非必要操作，避免干扰页面和产生噪声日志
                    # 周期性精准清除 Cookie 横幅（降频到 10s，避免阻塞实时预览）
                    if now - last_dismiss >= 10.0:
                        last_dismiss = now
                        self._dismiss_cookie_all_frames()
                    # 节流诊断：每 ~15s 打印一次真正可能拦截点击的遮挡元素
                    if now - last_diag >= 15.0:
                        last_diag = now
                        findings = self._diagnose_overlays()
                        if findings:
                            print("[ydf-recorder] overlays now visible:\n  " + "\n  ".join(findings), flush=True)
            except Exception as ex:
                print(f"[ydf-recorder] ⚠️ poll loop error: {ex}", flush=True)
            time.sleep(self._poll_interval_ms / 1000)

        # 最终采集一次，确保拿到停止前最后的事件
        self._events = self._capture_events()
        print(f"[ydf-recorder] Recording stopped. {len(self._events)} events captured.", flush=True)
        return self._events

    def collect_events(self) -> list[dict[str, Any]]:
        """直接获取当前已捕获的事件（不等待停止）。"""
        try:
            result = self._page.evaluate(
                "JSON.stringify(window.__ydf_recorder_dump ? window.__ydf_recorder_dump() : [])"
            )
            events = json.loads(result) if isinstance(result, str) else []
            return events
        except Exception:
            return []

    def resolve_menu_path(self, service_code: str) -> str | None:
        """录制停止后反查 serviceCode → 中文菜单路径。

        使用浏览器 context 的 request 通道（自动携带登录 cookies）拉取
        service_tree，再由 ``menu_resolver`` 反查。**必须在 ``stop()`` 前调用**
        （context 关闭后无法发请求）。
        """
        if not service_code or self._context is None:
            return None
        url = self.config.base_url.rstrip("/") + self.config.endpoints.service_tree
        try:
            response = self._context.request.get(url, timeout=20000)
            if not response.ok:
                return None
            payload = response.json()
        except Exception:
            return None
        return resolve_menu_path_from_tree(payload, service_code)

    def stop(self) -> None:
        """关闭检查器、目标上下文与浏览器，清理资源。"""
        for closer in (
            lambda: self._inspector_ctx.close() if self._inspector_ctx else None,
            lambda: self._context.close() if self._context else None,
            lambda: self._browser.close() if self._browser else None,
            lambda: self._playwright.stop() if self._playwright else None,
        ):
            try:
                closer()
            except Exception:
                pass

    @property
    def page(self):
        """暴露目标页对象，方便外部操作（如登录）。"""
        return self._page
