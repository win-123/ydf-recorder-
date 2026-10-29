## Why

同一测试集在 macOS 正常，但多台 Windows 电脑均在首个用例成功后、第二个用例创建 page 时失败，错误为 `BrowserContext.new_page: Target page, context or browser has been closed`。差分验证确认单独运行第二个用例和使用 `--no-persistent-profile` 均可通过，根因范围已收敛到持久化浏览器 context 在跨用例清理期间进入零 page 状态后的平台生命周期差异。

## What Changes

- 调整持久化浏览器 profile 的页面生命周期，跨用例清理和菜单切换期间保持 context 始终拥有一个可用 page，避免 Windows Chromium 结束 context。
- 继续关闭上一用例产生的业务 page，保留用例隔离，并在整个 run 结束时统一关闭 context。
- 增加可模拟 Windows Chromium 零 page 关闭行为的生命周期回归测试，覆盖关闭上一用例 page 后继续创建 page 的行为；保留现有 fake runtime 测试用于验证 CLI 调用顺序。
- 使用原 Windows 失败 DSL 做跨平台真实验证，不增加 DSL 字段或业务页面特例。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `browser-profile-lifecycle`: 收紧持久化 profile 的页面生命周期要求，跨用例和菜单 page 替换不得让共享 context 进入无可用 page 并失效的状态。

## Impact

- 运行时：`ydf_browser/runtime.py` 的 page 创建、替换和用例结束清理。
- 高层执行：必要时调整 `ydf_browser/cli.py` 对共享 runtime 的生命周期调用，但不改变命令行接口。
- 测试：`tests/test_runtime.py` 和相关 CLI 生命周期测试。
- 规格：`openspec/specs/browser-profile-lifecycle/spec.md`。
- 无新增依赖、无 DSL 语义变更、无破坏性变更。
