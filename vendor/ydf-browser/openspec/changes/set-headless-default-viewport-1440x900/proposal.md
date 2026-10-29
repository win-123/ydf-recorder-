## Why

无显式 `--window-size` 的 headless 运行当前继承 Playwright 默认 `1280×720` viewport，会让部分 YonDiF 动态工作面进入与常用有头窗口不同的响应式布局，并在 TI-001 中使底部“确定”动作无法被现有工具路径命中。为让默认无头回归使用稳定且更接近现有页面验证基线的布局，需要恢复 `1440×900` 的固定 headless viewport。

## What Changes

- **BREAKING**：未显式提供 `--window-size` 的 headless 持久化和非持久化运行，默认页面 viewport 从 Playwright 默认值改为 `1440×900`。
- 显式 `--window-size WIDTHxHEIGHT` 继续优先于默认值，允许调用方选择其它 headless viewport，包括显式恢复 `1280x720`。
- headed 浏览器继续使用 `no_viewport=True` 并跟随宿主窗口；不向未显式配置尺寸的 headed Chromium 注入 `--window-size`。
- 更新窗口尺寸文档和聚焦测试，并使用当前源码在默认 headless 模式下重跑 TI-001 原始真实 DSL。
- 本 change 只稳定默认无头布局，不修改 `dialog.click` 目标解析、前端页面或 DSL 结构。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `configurable-browser-window-size`: 将未显式配置尺寸的 headless 默认行为从保留 Playwright 默认 viewport 改为固定 `1440×900`，同时保持显式覆盖和 headed 行为不变。

## Impact

- 影响 `ydf_browser/runtime.py` 中持久化与非持久化 browser context 的默认 headless viewport 配置。
- 更新 `tests/test_runtime.py` 的默认与显式尺寸覆盖，并检查 `tests/test_cli.py` 的参数优先级回归。
- 更新 `README.md` 和 `docs/release/request-forwarding.md` 中关于默认 headless viewport 的说明。
- 不修改 `ams-pvdf`、DSL schema、登录与 profile 生命周期、请求转发、报告格式或退出码。
