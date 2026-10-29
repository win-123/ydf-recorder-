## ADDED Requirements

### Requirement: 嵌套 WUI 表格数据值断言
系统 SHALL 在表格数据值断言中正确处理 YonDiF 嵌套 WUI 表格的 header/body 分离渲染，并将读取限定在目标表格作用域内。

#### Scenario: 指定内部检查小组后读取成员列值
- **WHEN** DSL 文档执行 `table.assert_column_values`
- **AND** `target.table` 为 `内部检查小组`
- **AND** `target.column` 为 `人员名称`
- **AND** 页面中 `内部检查小组` 表格 body 存在 `财会监督1` 成员行
- **THEN** executor MUST 将 `target.table` 解析为目标表格作用域，并在可用时传递 `table_fieldid`
- **THEN** runtime MUST 将目标表头与对应 body 单元格关联
- **THEN** runtime MUST 返回 `人员名称` 列中的 `财会监督1`
- **AND** runtime MUST NOT 因 header root 不包含 body 而返回空值

#### Scenario: 行值断言复用同一表格簇映射
- **WHEN** DSL 文档执行 `table.assert_row_values`
- **AND** `target.table` 指向 header/body 分离的嵌套 WUI 表格
- **AND** `target.match` 能在对应 body 中匹配业务行
- **THEN** runtime MUST 在同一目标表格簇中定位业务行
- **THEN** runtime MUST 使用同一表格簇的列映射读取 `target.fields` 中的字段值
- **AND** runtime MUST NOT 从其它嵌套子表、固定列副本或背景列表表格读取值

#### Scenario: 分离表格读取失败时输出可解释诊断
- **WHEN** `table.assert_column_values` 或 `table.assert_row_values` 在指定表格作用域下无法读取目标值
- **THEN** 错误诊断 MUST 包含目标 `table`、可用时的 `table_fieldid`、目标列、当前目标表格 headers 和可见 row 文本摘要
- **AND** 如果页面全局调试文本中存在目标值但 scoped 读取为空，诊断 MUST 暴露表格 root 与 body 关联信息，方便定位 header/body 分离问题
