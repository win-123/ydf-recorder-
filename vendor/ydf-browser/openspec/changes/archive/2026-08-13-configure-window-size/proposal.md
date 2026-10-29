## Why

当前运行时默认强制使用 `1440×900`，这符合早期非持久化浏览器的验证需求，但会覆盖持久化浏览器已有的宿主窗口行为。现在需要让窗口尺寸成为显式选择，避免无参数启动时改变用户的浏览器布局。

## What Changes

- 移除运行时默认注入的 `1440×900` viewport 和 Chromium `--window-size`。
- 为 `ydf-browser run` 增加可选 `--window-size WIDTHxHEIGHT` 参数。
- headed 模式仅在显式传入参数时设置 Chromium 启动时的外层窗口尺寸，context 使用可变 viewport；headless 模式将显式尺寸应用到页面 viewport。
- 同时覆盖持久化和非持久化浏览器启动路径；未传参数时 headed 页面跟随宿主窗口，headless 页面保留 Playwright 默认 viewport。
- 对尺寸格式、正整数和启动模式进行参数校验，不改变登录、profile、请求转发或 DSL 语义。

## Capabilities

### New Capabilities

- `configurable-browser-window-size`: 定义浏览器窗口尺寸参数及其默认、headed 和 headless 行为。

### Modified Capabilities

无。

## Impact

- 影响 `ydf_browser/cli.py` 的命令参数解析和 `ydf_browser/runtime.py` 的 Playwright context/Chromium 启动参数。
- 增加 CLI 与运行时回归测试，并更新 README、发布使用说明和运行时 OpenSpec capability。
- 不新增依赖，不改变既有 DSL 用例的登录、profile、请求转发、报告和执行流程。
