## ADDED Requirements

### Requirement: 自定义弹窗动作关闭动态模板后自动恢复
当工作流在动态模板内执行非固定保存或确认标签的 `dialog.click`，且该动作关闭当前动态工作面并返回上一层模板时，executor SHALL 根据运行时 DOM 与 manifest 可见性证据自动恢复上一层模板上下文，不要求 DSL 显式配置 `restore_previous`。

#### Scenario: 去签章后恢复父列表
- **WHEN** 工作流从包含主表格的父列表进入动态编辑模板
- **AND** 在动态编辑模板内保存后执行 `dialog.click`，目标 label 为 `去签章`
- **AND** 该动作关闭动态编辑工作面，当前模板不再暴露前景稳定动作或可编辑字段身份
- **AND** 上一层列表模板在运行时可见且恢复证据强于当前模板
- **THEN** executor MUST 自动恢复上一层列表 manifest
- **AND** `dialog.click` 步骤结果 MUST 包含 `restored_template` 和 `auto_restored_template: true`
- **AND** 后续页签和表格操作 MUST 按已恢复的父列表 manifest 解析

#### Scenario: 自定义动作后动态表单仍活跃
- **WHEN** 工作流在动态模板内执行自定义 `dialog.click`
- **AND** 动作后当前动态模板仍暴露前景稳定动作或可编辑字段身份
- **THEN** executor MUST 保持当前动态模板
- **AND** `dialog.click` 步骤结果 MUST NOT 包含 `auto_restored_template: true`

#### Scenario: 自定义动作产生错误通知
- **WHEN** 工作流在动态模板内执行自定义 `dialog.click`
- **AND** 动作后捕获到错误通知
- **THEN** executor MUST 保持当前动态模板
- **AND** `dialog.click` 步骤结果 MUST NOT 包含 `auto_restored_template: true`

#### Scenario: 背景父模板可见但证据不足
- **WHEN** 工作流在动态模板内执行自定义 `dialog.click`
- **AND** 上一层模板仅作为背景保留部分可见元素
- **AND** 运行时证据不能证明当前动态工作面已关闭或上一层模板更适合作为活动上下文
- **THEN** executor MUST 保持当前动态模板
- **AND** executor MUST NOT 仅因上一层模板具有正可见性评分而自动恢复
