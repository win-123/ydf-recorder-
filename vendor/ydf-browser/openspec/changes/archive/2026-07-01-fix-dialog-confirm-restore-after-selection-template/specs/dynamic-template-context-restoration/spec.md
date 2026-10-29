## ADDED Requirements

### Requirement: 临时选择模板确认后恢复上一层表单模板
当工作流从动态表单模板内通过 `toolbar.click` 或 `action.click` 打开只有临时选择语义的动态模板时，executor SHALL 在 `dialog.confirm` 确认关闭该临时模板后自动恢复上一层表单模板上下文，不要求 DSL 显式配置 `restore_previous`。

#### Scenario: 工具栏选择确认后保存上一层表单
- **WHEN** 工作流通过 `toolbar.click` 进入动态表单模板
- **AND** 在该表单模板内继续执行 `toolbar.click` 打开仅包含 `确认/取消` 等临时选择动作的动态选择模板
- **AND** 工作流在选择模板内完成表格行选择后执行 `dialog.confirm`
- **AND** 确认后未捕获到错误通知
- **AND** 上一层表单模板重新成为可见工作面并包含 `保存` 动作
- **THEN** executor MUST 自动恢复上一层表单模板
- **AND** `dialog.confirm` 步骤结果 MUST 包含 `auto_restored_template: true`
- **AND** 后续 `toolbar.click 保存` MUST 在上一层表单模板中解析并点击保存动作

#### Scenario: 普通动作选择确认后保存上一层表单
- **WHEN** 工作流通过 `toolbar.click` 进入动态表单模板
- **AND** 在该表单模板内继续执行 `action.click` 打开仅包含 `确认/取消` 等临时选择动作的动态选择模板
- **AND** 工作流在选择模板内完成表格行选择后执行 `dialog.confirm`
- **AND** 确认后未捕获到错误通知
- **AND** 上一层表单模板重新成为可见工作面并包含 `保存` 动作
- **THEN** executor MUST 自动恢复上一层表单模板
- **AND** `dialog.confirm` 步骤结果 MUST 包含 `auto_restored_template: true`
- **AND** 后续 `toolbar.click 保存` MUST 在上一层表单模板中解析并点击保存动作

#### Scenario: 当前表单仍活跃时不恢复
- **WHEN** 工作流执行 `dialog.confirm`
- **AND** 当前动态模板仍暴露 `保存` 或其他保存类稳定表单动作
- **THEN** executor MUST 保持当前动态模板
- **AND** `dialog.confirm` 步骤结果 MUST NOT 包含 `auto_restored_template: true`
