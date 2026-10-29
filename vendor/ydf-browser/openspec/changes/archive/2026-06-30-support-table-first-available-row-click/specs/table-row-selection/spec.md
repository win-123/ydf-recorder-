## ADDED Requirements

### Requirement: first_available 选择无 checkbox 的首条有效业务行
系统 SHALL 将 `table_row_selection.select target.first_available` 解释为选择目标表格内第一条有效业务行；当该行没有 checkbox 或等效行选择控件时，runtime MUST 在已解析表格作用域内点击该业务行以触发表格原生选中。

#### Scenario: 目标表首条业务行没有 checkbox 时点击行
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.table` 唯一指向一张可见主表格
- **AND** `target.first_available` 为 `true`
- **AND** 该表格第一条有效业务行没有可见 checkbox 或等效行选择控件
- **THEN** runtime MUST 点击该业务行
- **AND** runtime MUST NOT 退回全页面裸文本点击
- **AND** 步骤结果 MUST 包含 `row_numbers: [1]`、`table`，并在可用时包含 `table_fieldid`

#### Scenario: 首条业务行存在 checkbox 时仍优先点击 checkbox
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.first_available` 为 `true`
- **AND** 第一条有效业务行包含可见 checkbox 或等效行选择控件
- **THEN** runtime MUST 优先点击该选择控件
- **AND** runtime MUST NOT 因新增行点击兜底而跳过选择控件

#### Scenario: first_available 忽略非业务行
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.first_available` 为 `true`
- **AND** 目标表格包含表头、`暂无数据` 占位行、小计行或合计行
- **THEN** runtime MUST NOT 将这些非业务行作为 first available 候选
- **AND** runtime MUST 继续查找第一条有效业务行

#### Scenario: 没有有效业务行时 first_available 失败
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.first_available` 为 `true`
- **AND** 已解析目标表格没有任何有效业务行
- **THEN** 步骤 MUST 失败
- **AND** 错误信息 MUST 说明未找到可选择的表格行号或未找到有效业务行，并包含目标表格诊断

#### Scenario: first_available 遵守多表格歧义规则
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.first_available` 为 `true`
- **AND** 未填写 `target.table`
- **AND** 当前页面存在多张可见主表格且无法唯一确定目标表格
- **THEN** 步骤 MUST 在点击任何行或选择控件前失败
- **AND** 错误信息 MUST 要求补充 `target.table`
