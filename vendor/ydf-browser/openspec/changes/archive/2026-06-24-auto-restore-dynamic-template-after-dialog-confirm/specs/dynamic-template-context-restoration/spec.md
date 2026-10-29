## ADDED Requirements

### Requirement: 弹窗确认后恢复已关闭的工具栏动态模板
当工作流通过 `toolbar.click` 从列表页进入动态弹窗或动态表单模板后，`dialog.confirm` 确认成功并让页面返回上一层列表时，executor SHALL 自动恢复上一层模板上下文，不要求 DSL 显式配置 `restore_previous`。

#### Scenario: 确认后从工具栏动态弹窗返回可查询列表
- **WHEN** 工作流从包含查询区和主表格的列表模板执行 `toolbar.click`
- **AND** 该动作捕获到动态弹窗或动态表单模板
- **AND** 工作流在动态模板内完成录入后执行 `dialog.confirm`
- **AND** 确认后未捕获到错误通知
- **AND** 当前动态模板不再暴露可见的稳定动作或可编辑字段身份
- **AND** 上一层列表模板可见
- **THEN** executor MUST 自动恢复上一层列表模板
- **AND** `dialog.confirm` 步骤结果 MUST 包含 `auto_restored_template: true`
- **AND** 后续 `query.search` MUST 能绑定上一层列表模板的查询字段

#### Scenario: 确认后保留仍活跃的工具栏动态表单
- **WHEN** 工作流从列表模板执行 `toolbar.click` 并进入动态表单模板
- **AND** 工作流执行 `dialog.confirm`
- **AND** 确认后当前动态表单仍暴露可见的稳定动作或可编辑字段身份
- **THEN** executor MUST 保持当前动态表单模板
- **AND** `dialog.confirm` 步骤结果 MUST NOT 包含 `auto_restored_template: true`

#### Scenario: 确认错误时保留工具栏动态表单
- **WHEN** 工作流从列表模板执行 `toolbar.click` 并进入动态表单模板
- **AND** 工作流执行 `dialog.confirm`
- **AND** 确认后捕获到错误通知
- **THEN** executor MUST 保持当前动态表单模板
- **AND** `dialog.confirm` 步骤结果 MUST NOT 包含 `auto_restored_template: true`
