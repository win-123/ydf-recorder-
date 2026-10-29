## ADDED Requirements

### Requirement: 页签切回父列表后恢复动态模板
当工作流在动态子模板中执行 `tab.click` 且页面实际切回父列表时，executor SHALL 根据当前模板与父模板的运行时可见性证据恢复父列表 manifest；当前动态模板仍是前景可操作面时 MUST 保持当前 manifest。

#### Scenario: 含主表格的子模板切回父列表
- **WHEN** 工作流从包含主表格的父列表进入动态子模板
- **AND** 子 manifest 自身声明一张或多张主表格
- **AND** `tab.click` 后子模板的稳定动作、可编辑字段和主表格均不再作为前景可操作面可见
- **AND** 父列表主表格可见且父模板的运行时恢复证据强于当前模板
- **THEN** executor MUST 自动恢复父列表 manifest
- **AND** `tab.click` 步骤结果 MUST 包含 `restored_template` 和 `auto_restored_template: true`
- **AND** 后续表格操作 MUST 按父列表 manifest 解析

#### Scenario: 页签点击后动态子模板仍活跃
- **WHEN** 工作流在动态子模板中执行 `tab.click`
- **AND** 父模板仍有背景元素可见或可扫描
- **AND** 当前动态模板仍暴露前景稳定动作或可编辑字段身份
- **THEN** executor MUST 保持当前动态模板
- **AND** executor MUST NOT 仅因父模板具有更高的正可见性评分而自动恢复
- **AND** `tab.click` 步骤结果 MUST NOT 包含 `auto_restored_template: true`
