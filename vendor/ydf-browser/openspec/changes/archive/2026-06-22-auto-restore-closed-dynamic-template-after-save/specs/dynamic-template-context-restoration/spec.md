## ADDED Requirements

### Requirement: 保存后自动恢复已关闭动态模板
保存或提交动态模板后，executor SHALL 根据运行时页面元素判断当前模板是否已经关闭或返回上一层；当当前动态模板不再是前景可操作面且上一层模板可见时，executor MUST 自动恢复上一层模板，不要求 DSL 显式配置 `restore_previous`。

#### Scenario: 保存返回父级表格模板
- **WHEN** 工作流从包含表格的父级模板进入动态子表单
- **AND** 子表单中 `toolbar.click` 目标为 `保存` 或 `提交`
- **AND** 未捕获到错误通知
- **AND** 子表单的稳定动作或字段身份不再作为前景可操作面可见
- **AND** 父级模板可见
- **THEN** executor MUST 自动恢复父级模板
- **AND** 步骤结果 MUST 包含 `auto_restored_template: true`
- **AND** 后续表格操作 MUST 在已恢复的父级模板上执行

#### Scenario: 保存校验错误保留子表单
- **WHEN** 工作流正在动态子表单中执行
- **AND** `toolbar.click` 目标为 `保存` 或 `提交`
- **AND** 捕获到错误通知
- **THEN** executor MUST 保持子表单为当前模板
- **AND** 步骤结果 MUST NOT 包含 `auto_restored_template: true`

#### Scenario: 保存后子表单仍可见
- **WHEN** 工作流正在动态子表单中执行
- **AND** `toolbar.click` 目标为 `保存` 或 `提交`
- **AND** 动作后子表单仍暴露可见的稳定动作或可编辑字段身份
- **THEN** executor MUST 保持子表单为当前模板
- **AND** executor MUST NOT 仅因为上一层模板存在可见背景元素就自动恢复
