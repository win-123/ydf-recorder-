## 1. 回归测试

- [x] 1.1 在 `tests/test_runtime.py` 增加会在最后一个 page 关闭时使 context 失效的最小 fake context，复现 Windows 报告中的 `Target page, context or browser has been closed`。
- [x] 1.2 增加跨用例清理和连续 `open_menu` 的生命周期测试，并确认测试在实现修复前失败。

## 2. 运行时修复

- [x] 2.1 调整 `PlaywrightRuntime.close_case_pages()`，先创建 run-scope holder page，再关闭当前用例业务 pages，确保共享 context 不进入零 page 状态。
- [x] 2.2 调整持久化模式的菜单 page 替换，先创建并接管新业务 page，再关闭旧 page，同时复用现有事件监听和 cookies 状态重置逻辑。
- [x] 2.3 检查 `close_case_pages()`、菜单替换和 run 结束 `stop()` 的全部调用方，确认临时 context 语义和真实崩溃错误传播不变。

## 3. 验证

- [x] 3.1 运行新增生命周期测试及相邻 runtime、CLI 聚焦测试，确认零 page 模拟和既有页面隔离语义均通过。
- [x] 3.2 在 macOS 使用当前源码运行原失败 DSL，确认两个用例在默认持久化 profile 模式下通过。
- [x] 3.3 由同事在 Windows 使用修复版本运行原失败 DSL，确认无需 `--no-persistent-profile` 即可连续完成两个用例。
- [x] 3.4 运行完整 `./.venv/bin/python -m pytest`，确认共享 runtime 修改没有回归。

## 4. 规格与交付检查

- [x] 4.1 同步检查 `browser-profile-lifecycle` 规格与实现一致，并运行 `openspec validate fix-persistent-context-zero-page-lifecycle --strict`。
- [x] 4.2 运行 `./scripts/check_openspec_language.py --change fix-persistent-context-zero-page-lifecycle` 和 `git diff --check`。
