## MODIFIED Requirements

### Requirement: 按行号选择无 checkbox 行必须点击真实可接收事件的业务行
系统 SHALL 在 `table_row_selection.select` 使用 `target.row_number` 或 `target.first_available` 定位无 checkbox 业务行时，点击目标表格内真实可接收 pointer 事件的业务行区域；优先确认目标行进入真实选中/当前行状态，页面未暴露可读选中态时必须带出未确认但已点击真实业务行的诊断。

#### Scenario: 调出方无 checkbox 行点击后确认选中
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.table` 为 `调出方`
- **AND** `target.row_number` 为 `1`
- **AND** 目标表格第一条有效业务行没有可见 checkbox 或等效行选择控件
- **THEN** runtime MUST 在已解析的 `调出方` 表格作用域内点击可接收 pointer 事件的业务行单元格
- **AND** runtime MUST NOT 点击被表单、旧 DOM 或其它层覆盖的同文本行
- **AND** runtime SHOULD 在点击后确认目标行或等效当前行 DOM 出现真实选中证据
- **AND** 当页面未暴露可读选中证据但点击目标是真实可接收事件的业务行单元格时，步骤结果 MUST 包含 `accepted_unconfirmed=true`
- **AND** 步骤结果 MUST 包含 `row_numbers: [1]`、`table`、可用时的 `table_fieldid`，以及行点击诊断

#### Scenario: 行点击无法命中真实可接收业务行时失败
- **WHEN** runtime 已按行号找到目标业务行
- **AND** 该行没有可点击的行选择 checkbox 或等效行选择控件
- **AND** 该行或其对齐业务单元格无法通过 `elementFromPoint` 确认可接收 pointer 事件
- **THEN** `table_row_selection.select` MUST 失败
- **AND** 错误信息 MUST 说明未找到可选择的表格行
- **AND** 错误诊断 MUST 包含目标 `table`、可用时的 `table_fieldid`、行号和表格根摘要

#### Scenario: fieldid 命中无可选业务行时不得按表名回退
- **WHEN** `target.table` 为 `调出方`
- **AND** executor 已将 `target.table` 解析为 `table_fieldid`
- **AND** runtime 已根据 `table_fieldid` 找到表格根
- **AND** 该表格根内不存在可接收 pointer 事件的有效业务行
- **THEN** `table_row_selection.select` MUST 在点击其它表格前失败
- **AND** runtime MUST NOT 按 `target.table` 的可见标题重新解析其它表格根
- **AND** 错误诊断 MUST 包含目标 `table`、`table_fieldid` 和已命中的表格根摘要
- **AND** runtime MUST 继续支持同一 `table_fieldid` 表格内 WUI 表头和表体分裂 DOM 的聚合

## ADDED Requirements

### Requirement: 表格行选择实际表格根诊断
系统 SHALL 在 `table_row_selection.select` 成功后记录 runtime 实际命中的表格根摘要，使报告能区分 DSL 声明目标和真实 DOM 点击作用域。

#### Scenario: 成功选择时记录实际根身份
- **WHEN** `table_row_selection.select` 成功选中一行
- **AND** runtime 已解析出表格根
- **THEN** 步骤结果 MUST 包含实际表格根诊断
- **AND** 诊断 MUST 在可用时包含 root `fieldid`、`source` 和 `selectableRows`
- **AND** 诊断 MUST NOT 只复述 DSL 中的 `target.table`

#### Scenario: 未暴露根身份时仍保留选择诊断
- **WHEN** `table_row_selection.select` 成功选中一行
- **AND** runtime 无法从 DOM 根读取 root `fieldid`
- **THEN** 步骤结果 MUST 保留已有选择诊断
- **AND** 诊断 MUST 在可用时包含 root `source`、`rows` 或 `selectableRows`
