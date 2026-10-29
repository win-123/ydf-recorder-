## ADDED Requirements

### Requirement: 弹窗保存后恢复已关闭动态模板
当工作流在动态模板内通过 `dialog.click` 点击 `保存` 或 `提交`，且该动作关闭当前动态弹窗并返回上一层模板时，executor SHALL 自动恢复上一层模板上下文，不要求 DSL 显式配置 `restore_previous`。

#### Scenario: 保存弹窗后继续保存上一层表单
- **WHEN** 工作流从列表模板通过 `toolbar.click` 进入动态表单模板
- **AND** 在该表单模板内继续通过 `toolbar.click` 打开动态弹窗模板
- **AND** 工作流在动态弹窗中执行 `dialog.click`，目标 label 为 `保存`
- **AND** 未捕获到错误通知
- **AND** 当前动态弹窗的稳定动作或字段身份不再作为前景可操作面可见
- **AND** 上一层动态表单模板可见
- **THEN** executor MUST 自动恢复上一层动态表单模板
- **AND** `dialog.click` 步骤结果 MUST 包含 `auto_restored_template: true`
- **AND** 后续 `toolbar.click 保存` MUST 在上一层动态表单模板中解析

#### Scenario: 弹窗保存错误时保留当前模板
- **WHEN** 工作流正在动态弹窗模板中执行 `dialog.click`
- **AND** 目标 label 为 `保存` 或 `提交`
- **AND** 捕获到错误通知
- **THEN** executor MUST 保持当前动态弹窗模板
- **AND** `dialog.click` 步骤结果 MUST NOT 包含 `auto_restored_template: true`

#### Scenario: 弹窗保存后仍活跃时不恢复
- **WHEN** 工作流正在动态弹窗模板中执行 `dialog.click`
- **AND** 目标 label 为 `保存` 或 `提交`
- **AND** 动作后当前动态弹窗仍暴露可见的稳定动作或可编辑字段身份
- **THEN** executor MUST 保持当前动态弹窗模板
- **AND** executor MUST NOT 仅因为上一层模板存在可见背景元素就自动恢复
