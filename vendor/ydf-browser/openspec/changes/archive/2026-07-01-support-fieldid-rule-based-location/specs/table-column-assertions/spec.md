## ADDED Requirements

### Requirement: 表格定位使用规则推导身份
系统 SHALL 在表格行选择、列值采集、列断言和可编辑表格录入中，使用 `LCDTable` 的 `divCode`、表格运行时 `fieldid`、列 `dataField` 和固定表头/表体身份推导目标表格与列。

#### Scenario: 表格根和表头表体身份可推导
- **WHEN** 模板中表格容器 `divCode=userTable`
- **THEN** executor MUST 可将该表格运行时根身份解析为 `userTable_table`
- **AND** runtime MUST 可在该表格根内使用 `table-header` 和 `table-body` 识别表头、表体和数据行

#### Scenario: 表格列使用 table fieldid and dataField
- **WHEN** 目标表格运行时身份为 `userTable_table`
- **AND** 目标列模板 `dataField=code`
- **THEN** runtime MUST 优先尝试列身份 `userTable_table_code` 或等价 DOM identity 定位表头和单元格
- **AND** 如果身份冲突或缺失，runtime MUST 保留现有表头文本和表格作用域兜底诊断
