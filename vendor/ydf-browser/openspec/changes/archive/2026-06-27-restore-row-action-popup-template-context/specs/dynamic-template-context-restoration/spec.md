## ADDED Requirements

### Requirement: 行级动作弹出参照关闭后恢复上一层模板
当 `table_row_action.click` 直接打开动态弹出参照模板时，executor SHALL 在 `popup_reference.select` 完成并确认参照模板已关闭后恢复上一层活动模板。

#### Scenario: 选择库存后恢复包含两个可编辑表格的分配页
- **WHEN** 工作流在分配页执行 `table_row_action.click`，目标行为 `选择库存`
- **AND** 该动作捕获到包含候选表格和 `确定/取消` 动作的动态参照模板
- **AND** `popup_reference.select` 完成选择并关闭参照模板
- **AND** 上一层分配页模板重新可见，当前参照模板的稳定动作身份不再可见
- **THEN** executor MUST 恢复上一层分配页模板
- **AND** `popup_reference.select` 步骤结果 MUST 包含 `auto_restored_template: true`
- **AND** 后续 `editable_table.fill_row target.table=物资申请出库信息` MUST 按分配页模板解析，不得使用已关闭参照模板中的通用表格标签 `表格`

#### Scenario: 行级编辑表单仍活跃时不恢复到列表
- **WHEN** 工作流通过 `table_row_action.click` 进入动态编辑表单
- **AND** 工作流执行 `popup_reference.select`
- **AND** 参照关闭后当前编辑表单仍暴露可见的稳定动作或字段身份
- **THEN** executor MUST 保持当前编辑表单模板
- **AND** executor MUST NOT 仅因为上一层列表存在可扫描元素就自动恢复

#### Scenario: 既有工具栏参照恢复保持兼容
- **WHEN** 工作流通过 `toolbar.click` 或 `action.click` 打开动态弹出参照模板
- **AND** `popup_reference.select` 完成后上一层模板重新成为活动可见面
- **THEN** executor MUST 保持既有自动恢复行为
