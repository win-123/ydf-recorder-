## ADDED Requirements

### Requirement: 嵌套 WUI 表格行选择
系统 SHALL 在指定表格作用域后，支持 YonDiF 嵌套 WUI 表格的业务行选择，即使该表格的 header 和 body 分离渲染。

#### Scenario: 指定内部检查小组后选择成员行
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.table` 为 `内部检查小组`
- **AND** `target.match.column` 为 `人员名称`、`target.match.equals` 为 `财会监督1`
- **AND** 页面中 `内部检查小组` 表格 body 存在包含 `财会监督1` 的可选择数据行
- **THEN** executor MUST 将 `target.table` 解析为该子表作用域，并在可用时传递 `table_fieldid`
- **THEN** runtime MUST 将 header 与对应 body 关联为同一目标表格
- **THEN** runtime MUST 在该表格 body 中勾选目标行 checkbox
- **AND** runtime MUST NOT 在其它表格或全页面裸文本范围内选择同名行

#### Scenario: Header root 不含 body 时仍能选择行
- **WHEN** 目标 WUI 表格的 `.wui-table-header` 和 `.wui-table-body` 是分离 DOM 容器
- **AND** fieldid 或表名首先命中 header 相关容器
- **THEN** runtime MUST 通过目标 fieldid、表头集合、几何位置或共同祖先找到对应 body 容器
- **THEN** runtime MUST 在对应 body 容器中执行行匹配和 checkbox 点击

#### Scenario: 目标行存在但无法选择时提供作用域诊断
- **WHEN** `table_row_selection.select` 在指定表格作用域内无法勾选目标行
- **THEN** 错误诊断 MUST 包含目标 `table`、可用时的 `table_fieldid`、目标列、匹配值、解析到的表格根摘要和可见行摘要
- **AND** 错误诊断 MUST 能区分目标表格无数据、列名不匹配和表格 root 不含 body 的情况
