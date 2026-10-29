## ADDED Requirements

### Requirement: 表格断言消费统一表格作用域
系统 MUST 在执行 `table.assert_columns`、`table.assert_column_values` 或 `table.assert_row_values` 前解析唯一表格作用域，并将 `present` 列、目标值列、行匹配列和字段列作为动作必需列进行预校验。`absent` 列 SHALL 作为否定断言保留，MUST NOT 被当作必需存在列。

#### Scenario: 列值断言在采集前校验目标列
- **WHEN** `table.assert_column_values` 声明目标列
- **THEN** 系统 MUST 在采集单元格值前确认目标列属于唯一表格作用域
- **AND** 目标列缺失时 MUST 直接报告列预校验失败

#### Scenario: absent 列不参与必需列预校验
- **WHEN** `table.assert_columns` 仅声明 `target.absent`
- **THEN** 系统 MUST 解析唯一表格作用域后采集真实表头
- **AND** 系统 MUST NOT 因 `absent` 中声明的列不存在而在断言前失败
