## ADDED Requirements

### Requirement: fieldid 表格根候选必须优先前景业务行
系统 SHALL 在 `table_row_selection.select` 已通过当前 manifest 将 `target.table` 解析为 `table_fieldid` 时，只在该 `table_fieldid` 对应的 DOM 候选内选择表格根，并优先选择当前前景、可见、包含可接收 pointer 事件业务行的候选根。

#### Scenario: 同 fieldid 背景旧根有 checkbox 时仍选择前景业务行根
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.table` 为 `调出方`
- **AND** 当前 manifest 将 `调出方` 解析为 `table_fieldid=table1`
- **AND** 页面 DOM 中同时存在多个 `table1_drag` 或 `table1` 候选根
- **AND** 背景旧候选根包含 `selectableRows` 但没有可接收 pointer 事件的有效业务行
- **AND** 前景候选根没有可见 checkbox，但第一条业务行存在可接收 pointer 事件的业务单元格
- **THEN** runtime MUST 选择前景候选根作为 `table_row_selection.select` 的实际表格根
- **AND** runtime MUST 点击前景候选根内第一条业务行的可接收业务单元格
- **AND** runtime MUST NOT 因背景旧候选根的 `selectableRows` 较高而选择背景旧根

#### Scenario: fieldid 已解析时不得按表名文本回退
- **WHEN** executor 已将 `target.table` 解析为 `table_fieldid`
- **AND** runtime 在该 `table_fieldid` 的 DOM 候选中找不到任何可接收 pointer 事件的有效业务行
- **THEN** `table_row_selection.select` MUST 在点击其它表格前失败
- **AND** runtime MUST NOT 按 `target.table` 的可见标题或文本重新全局匹配其它表格根
- **AND** 错误诊断 MUST 包含目标 `table`、`table_fieldid` 和已命中的 fieldid 候选根摘要

#### Scenario: 保持 WUI 表头表体分裂聚合
- **WHEN** `table_fieldid` 对应的 WUI 表格表头和表体位于分裂 DOM 结构中
- **AND** 表头候选和表体候选需要聚合后才能表示完整表格根
- **THEN** runtime MUST 继续聚合该 fieldid 内的表头和表体候选
- **AND** 前景业务行优先级 MUST 基于聚合后的表格根计算
- **AND** runtime MUST NOT 为了前景判断破坏既有列匹配、checkbox 优先或无 checkbox 行点击兜底行为
