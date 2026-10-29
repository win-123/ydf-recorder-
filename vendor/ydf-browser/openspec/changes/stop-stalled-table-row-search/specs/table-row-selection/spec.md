## ADDED Requirements

### Requirement: 表格行搜索限制无进展展开重试
系统 SHALL 在表格行搜索中限制同一疑似树表展开候选的无进展重试；候选达到有限重试次数后 MUST 跳过该候选，并继续检查其它候选或滚动当前表格作用域。

#### Scenario: 普通表格中的疑似展开候选不阻塞搜索
- **WHEN** `table_row_selection.select` 已限定到一个普通表格作用域
- **AND** 目标行当前不可见
- **AND** 作用域内某个疑似展开候选在点击和事件派发后均未改变可见业务行
- **AND** 该候选仍呈现未展开状态
- **THEN** runtime MUST 只对该候选执行有限次数的重试
- **AND** runtime MUST 在达到上限后跳过该候选
- **AND** runtime MUST NOT 因该候选耗尽整次表格行搜索的通用轮数上限

#### Scenario: 无效候选之后继续搜索当前表格
- **WHEN** 当前表格作用域中的一个疑似展开候选达到无进展重试上限
- **AND** 同一作用域仍存在其它未尝试候选或可继续滚动的表体
- **THEN** runtime MUST 继续检查其它候选或滚动当前表格
- **AND** runtime MUST NOT 扩大到其它表格作用域

#### Scenario: 真实树表展开仍可继续
- **WHEN** 树形表格中的展开候选点击后改变了可见业务行
- **THEN** runtime MUST 将该候选视为已展开并继续查找目标行
- **AND** 后续层级需要展开时 runtime MUST 继续处理新的未尝试候选
