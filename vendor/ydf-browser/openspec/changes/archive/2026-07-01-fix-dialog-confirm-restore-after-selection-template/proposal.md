## Why

部门预算调剂管理冻结流程中，`toolbar.click 选择` 或等效的 `action.click selectInfoBtn` 会打开一个临时指标选择模板。确认关闭该模板后页面实际回到冻结单新增页，但 executor 仍保留临时选择模板上下文，导致后续 `toolbar.click 保存` 失败为 `未绑定工具栏动作: 保存`。

## What Changes

- 调整 `dialog.confirm` 后的动态模板恢复判断：当当前动态模板是只有 `确认/取消` 等临时选择动作的选择模板，且上一层表单模板已经重新可见时，自动恢复上一层模板。
- 同时覆盖 `toolbar.click` 和 `action.click` 两种打开临时选择模板的入口。
- 保留已有保护：当前动态编辑表单仍暴露 `保存` 等稳定表单动作时，不得误恢复到背景列表。

## Capabilities

### New Capabilities

### Modified Capabilities
- `dynamic-template-context-restoration`: 增加临时选择模板在 `dialog.confirm` 后恢复上一层表单模板的要求。

## Impact

- 影响 `ydf_browser/executor.py` 的动态模板恢复判断。
- 增加 executor 回归测试，覆盖 `toolbar.click` 与 `action.click` 打开同类选择模板后确认恢复。
- 真实验证目标为部门预算调剂管理冻结流程，两种 DSL 写法均需执行到保存步骤之后。
