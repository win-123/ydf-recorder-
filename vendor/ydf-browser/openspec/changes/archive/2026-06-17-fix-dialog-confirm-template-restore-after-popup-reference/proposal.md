## Why

真实用例 `功能-网上报销-资金结算-生成支付单-按钮-0020.yaml` 在行级编辑后选择付款账户，再确认业务弹窗，后续点击 `保存` 失败为 `未绑定工具栏动作: 保存`。根因是 executor 将业务确认框的 `确定` 误判为编辑页关闭动作，自动恢复到列表页 manifest，导致当前模板上下文丢失。

## What Changes

- 收窄 `dialog.confirm` 后的自动恢复策略：确认框关闭后，只有在当前动态模板不再可见或当前页面确实回到上一层列表时才恢复上一层 manifest。
- 在弹出参照后的业务确认场景中保留当前编辑页动态模板，使后续 `toolbar.click 保存` 继续基于编辑页动作候选执行。
- 为该场景补充回归测试，覆盖 `table_row_action.click 编辑 -> toolbar.click 选择付款账户 -> popup_reference.select -> dialog.confirm 确定 -> toolbar.click 保存`。
- 保持已有“保存/取消后真实返回列表”的自动恢复行为不退化。

## Capabilities

### New Capabilities
- `dynamic-template-context-restoration`: 约束动态模板、弹窗、参照和上一层模板之间的上下文恢复行为，防止运行时仍处于编辑页时误恢复到列表页。

### Modified Capabilities

## Impact

- 主要影响 `ydf_browser/executor.py` 中动态模板栈和 `dialog.confirm` 自动恢复判断。
- 需要补充 `tests/test_executor.py` 中的单元回归，并用真实 YAML 复现验证。
- 不改变 DSL 语法，不引入新的运行时依赖。
