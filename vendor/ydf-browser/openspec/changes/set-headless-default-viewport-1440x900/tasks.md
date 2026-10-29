## 1. 回归测试先行

- [x] 1.1 在 `tests/test_runtime.py` 增加 persistent 与 ephemeral headless 未显式传入尺寸时 context viewport 均为 `1440×900`、不设置 `no_viewport` 且不传 Chromium `--window-size` 的参数化测试，并先运行该测试确认当前实现红灯。
- [x] 1.2 补强现有组合测试，覆盖显式 `--window-size 1600x1000` 仍优先、显式 `1280x720` 可恢复旧布局，以及 persistent/ephemeral headed 未显式传入尺寸时继续使用 `no_viewport=True`；运行相关测试确认除新增默认语义外没有回归。

## 2. 默认 headless viewport 实现

- [x] 2.1 在 `ydf_browser/runtime.py` 的共享 browser context 参数构造处为无显式尺寸的 headless 运行注入 `1440×900` viewport，并复用或提取单一运行时尺寸基线；运行 1.1 的参数化测试确认 persistent 与 ephemeral 路径均通过。
- [x] 2.2 保持 headless 显式尺寸优先、headed `no_viewport=True` 和 Chromium 启动参数分支不变，并运行 1.2 的组合测试确认实际参数符合规格。

## 3. 用户文档同步

- [x] 3.1 更新 `ydf_browser/cli.py` 的 `--window-size` 帮助说明，明确 headless 默认 `1440×900` 且显式值可覆盖；运行 `tests/test_cli.py` 的帮助与窗口尺寸解析测试确认 CLI 格式和优先级未改变。
- [x] 3.2 更新 `README.md` 与 `docs/release/request-forwarding.md`，删除“headless 保留 Playwright 默认 viewport”的旧表述，说明默认值、显式覆盖和 headed 不变行为；使用 `rg` 检查相关文档不再保留冲突说明。

## 4. 真实验证与交付门禁

- [x] 4.1 使用当前源码、不传 `--window-size` 分别运行用户提供的两个 TI-001 原始真实 DSL 复现用例，并将报告写到仓库外临时目录；确认行编辑动态工作面内的 `dialog.click 确定` 步骤实际成功，失败时保留报告和诊断文件且不得宣称修复完成。
- [x] 4.2 运行 `./.venv/bin/python -m pytest -q tests/test_runtime.py tests/test_cli.py -k "window_size or viewport"`，确认窗口尺寸聚焦回归通过。
- [x] 4.3 运行完整 `./.venv/bin/python -m pytest -q`，确认共享 runtime 默认行为变化没有破坏相邻 DSL 运行路径。
- [x] 4.4 运行 `openspec validate set-headless-default-viewport-1440x900 --strict`、`./scripts/check_openspec_language.py --change set-headless-default-viewport-1440x900` 和 `git diff --check`，确认结构、语言及最终差异均通过门禁。
