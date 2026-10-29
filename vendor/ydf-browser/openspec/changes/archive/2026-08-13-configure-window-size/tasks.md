## 1. 测试先行

- [x] 1.1 在 `tests/test_cli.py` 增加 `--window-size WIDTHxHEIGHT` 的合法与非法参数解析测试。
- [x] 1.2 在 `tests/test_runtime.py` 增加无尺寸时不传 viewport/Chromium 参数、显式尺寸覆盖 persistent/ephemeral headed 和 headless 的测试。
- [x] 1.3 运行新增聚焦测试，确认它们在旧实现下按预期失败。

## 2. CLI 与运行时实现

- [x] 2.1 在 `ydf_browser/cli.py` 增加可选 `--window-size` 参数并在浏览器启动前校验正整数尺寸。
- [x] 2.2 在 `ydf_browser/runtime.py` 将窗口尺寸改为可选配置，未传时不设置固定 viewport 或 Chromium `--window-size`。
- [x] 2.3 在 persistent、ephemeral、headed 和 headless 启动路径应用显式尺寸，保持既有 profile、登录和转发流程。

## 3. 文档与验证

- [x] 3.1 更新 `README.md` 和 `docs/release/request-forwarding.md`，说明默认行为和 `--window-size WIDTHxHEIGHT` 用法。
- [x] 3.2 运行聚焦测试、`openspec validate configure-window-size --strict`、`./scripts/check_openspec_language.py --change configure-window-size`、完整 `./.venv/bin/python -m pytest` 和 `git diff --check`。

## 4. 修复 headed viewport 跟随窗口

- [x] 4.1 增加 persistent 与 ephemeral headed context 的 `no_viewport=True` 回归测试，并确认旧实现失败。
- [x] 4.2 在无显式尺寸的 headed runtime 中设置 `no_viewport=True`，为后续显式启动尺寸的可变 viewport 行为提供基础。
- [x] 4.3 重新运行聚焦测试、真实 DSL、全量 pytest 和 OpenSpec 校验。

## 5. 修复显式启动尺寸后的窗口跟随

- [x] 5.1 更新 persistent 与 ephemeral headed 的回归测试，要求显式尺寸只传 Chromium 启动参数且 context 使用 `no_viewport=True`；headless 继续使用显式 viewport。
- [x] 5.2 应用最小 runtime 修复，并更新规格和用户文档，明确 `--window-size` 只改变启动时尺寸。
- [x] 5.3 重新运行真实窗口缩放、真实 DSL、全量 pytest 和 OpenSpec 校验。
