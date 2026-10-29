## ADDED Requirements

### Requirement: WUI 表格列身份映射
系统 SHALL 在 `table_row_selection.select` 使用 `target.match.column` 和 `target.match.equals` 时，支持 WUI 表格中模板表头身份与运行时行单元格身份不完全相同但语义一致的列值匹配。

#### Scenario: 表头 fieldid 与行单元格 data-index 对齐
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.match.column` 为 `政府采购标识`
- **AND** `target.match.equals` 为 `否`
- **AND** 目标表格表头 `政府采购标识` 的 DOM identity 为 `kyzb_table_isGovPurName`
- **AND** 同一业务行的目标单元格 DOM identity 为 `isGovPurName`
- **AND** 该单元格显示文本为 `否`
- **THEN** runtime MUST 将 `kyzb_table_isGovPurName` 与 `isGovPurName` 识别为同一模板列
- **AND** runtime MUST 使用该单元格值定位业务行
- **AND** runtime MUST 点击同一业务行的行选择 checkbox 或等效行选择控件
- **AND** runtime MUST NOT 因 WUI 单元格内部 wrapper 造成的可见 cell 索引偏移而漏选目标行
