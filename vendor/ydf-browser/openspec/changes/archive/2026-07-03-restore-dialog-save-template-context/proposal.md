## Why

真实用例在动态项目认领表单内打开开票弹窗，`dialog.click 保存` 关闭弹窗后没有恢复上一层表单模板，导致后续 `toolbar.click 保存` 只晚恢复一层，最终列表页 `提交` 被当前错误 manifest 拦截为 `未绑定工具栏动作: 提交`。

## What Changes

- 扩展动态模板恢复规则：`dialog.click` 点击 `保存` 或 `提交` 后，如果当前动态弹窗已关闭且上一层模板可见，自动恢复上一层模板。
- 保持现有错误通知保护和当前表单仍活跃时不恢复的保护。
- 增加 executor 回归测试，并用真实来款认领 DSL 验证保存开票弹窗、保存认领单、切待提交页签和提交链路。

## Capabilities

### New Capabilities

### Modified Capabilities
- `dynamic-template-context-restoration`: 补充 `dialog.click 保存/提交` 关闭动态弹窗后的模板上下文恢复要求。

## Impact

- 影响 `ydf_browser/executor.py` 的 `dialog.click` 后处理。
- 影响回归测试 `tests/test_executor.py`。
- 不改变 DSL schema，不新增依赖。
