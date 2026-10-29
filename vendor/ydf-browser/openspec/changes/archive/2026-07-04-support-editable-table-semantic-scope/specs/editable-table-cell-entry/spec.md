## ADDED Requirements

### Requirement: 可编辑表格 table 作用域支持语义标题和表身份
系统 SHALL 在执行 `editable_table.add_row` 或 `editable_table.fill_row` 时，将 `target.table` 解析为当前模板中的目标可编辑表格作用域，并支持用户使用可见语义标题、表 region `fieldid` 或 runtime fieldid 定位目标表格。

#### Scenario: 使用父卡片标题定位可编辑表格
- **WHEN** DSL 文档执行 `editable_table.fill_row`
- **AND** `target.table` 为用户界面可见的父卡片标题 `指标挂接规则`
- **AND** 当前模板中该父卡片下唯一可编辑表格的 region `fieldid` 为 `table_rule`
- **THEN** 系统 MUST 将该步骤限定到 `table_rule` 对应的可编辑表格
- **AND** 系统 MUST 继续使用该表格的模板列身份定位目标单元格

#### Scenario: 父标题下同时存在编辑表和展示表
- **WHEN** DSL 文档执行 `editable_table.fill_row`
- **AND** `target.table` 为父卡片标题 `指标挂接规则`
- **AND** 当前模板中 `table_rule` 和 `table_rule_view` 均位于该父卡片下且均包含列 `部门支出经济分类`
- **AND** 当前运行时 DOM 中只有 `table_rule` 对应表根存在且可见
- **THEN** 系统 MUST 将该步骤限定到 `table_rule` 对应的可编辑表格
- **AND** 系统 MUST NOT 因父标题匹配到多张表而拒绝该步骤

#### Scenario: 父标题下多张候选表同时可见时要求显式 fieldid
- **WHEN** DSL 文档执行 `editable_table.fill_row`
- **AND** `target.table` 为父卡片标题 `指标挂接规则`
- **AND** 当前模板中 `table_rule` 和 `table_rule_view` 均位于该父卡片下
- **AND** 当前运行时 DOM 中 `table_rule` 和 `table_rule_view` 对应表根都存在且可见
- **THEN** 当前步骤 MUST 失败
- **AND** 错误信息 MUST 提示这种情况下必须使用表 region `fieldid` 或 runtime fieldid 标识目标表格
- **AND** 系统 MUST NOT 继续依据列属性、列名或候选顺序猜测目标表格

#### Scenario: 使用 runtime fieldid 定位可编辑表格
- **WHEN** DSL 文档执行 `editable_table.fill_row`
- **AND** `target.table` 为目标表格的 runtime fieldid `table_rule_table`
- **AND** 当前模板中存在 region `fieldid=table_rule` 且其 `runtime_fieldids` 包含 `table_rule_table`
- **THEN** 系统 MUST 将该步骤限定到 `table_rule` 对应的可编辑表格
- **AND** 系统 MUST NOT 因表 region 的显示 label 为泛名 `表格` 而拒绝该步骤

#### Scenario: 表名不匹配时提示可用 fieldid
- **WHEN** DSL 文档执行 `editable_table.fill_row`
- **AND** `target.table` 未匹配当前模板中的任何可编辑表格作用域
- **THEN** 当前步骤 MUST 失败
- **AND** 错误信息 MUST 列出当前模板可用可编辑表格的 label、region `fieldid` 和 runtime fieldid
- **AND** 错误信息 MUST NOT 只重复输出多个无区分度的 `表格`

#### Scenario: 父级语义标题不唯一且运行时不可判定时不猜测
- **WHEN** DSL 文档执行 `editable_table.fill_row`
- **AND** `target.table` 匹配多个可编辑表格共享的父级语义标题
- **AND** 运行时 DOM 无法判定唯一可见目标表格
- **THEN** 当前步骤 MUST 失败
- **AND** 错误信息 MUST 列出冲突候选的 label、region `fieldid` 和 runtime fieldid
- **AND** 系统 MUST NOT 任意选择第一张匹配表格
