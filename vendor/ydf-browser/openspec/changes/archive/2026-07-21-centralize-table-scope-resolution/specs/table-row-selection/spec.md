## ADDED Requirements

### Requirement: 表格行选择消费统一表格作用域
系统 MUST 在执行 `table_row_selection.select` 前通过统一表格作用域能力解析目标表格和匹配条件引用列。runtime MUST 只在解析结果限定的表格内执行行匹配、树形展开、checkbox 选择或业务行点击。

#### Scenario: 复合条件列在选择前完成预校验
- **WHEN** `target.match.conditions` 引用多个列
- **THEN** 系统 MUST 在扫描业务行前确认全部列属于同一已解析表格
- **AND** 任一列缺失时步骤 MUST 失败且不得点击页面

#### Scenario: runtime 不按旧参数回退其它表格
- **WHEN** 已解析表格作用域的运行时根内不存在目标业务行
- **THEN** 当前步骤 MUST 按目标表格无匹配行失败
- **AND** runtime MUST NOT 使用原始 `target.table`、可见标题或全页面文本另行解析其它表格
