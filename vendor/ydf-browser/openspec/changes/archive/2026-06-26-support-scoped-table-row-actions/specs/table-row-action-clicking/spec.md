## ADDED Requirements

### Requirement: 表格行按钮支持指定表格作用域
系统 SHALL 支持 `table_row_action.click` 通过 `target.table` 或 `target.table_name` 指定目标表格，并在该表格作用域内定位业务行后点击行级按钮。

#### Scenario: 在指定可编辑表格内点击行按钮
- **WHEN** DSL 文档执行 `table_row_action.click`
- **AND** `target.table` 为 `物资信息`
- **AND** `target.action` 为 `选择库存`
- **AND** `target.row_number` 为 `1`
- **AND** 当前编辑页中 `物资信息` 表格可解析为 `table_fieldid=wzxx_table`
- **AND** 该表第 1 条可见业务行 hover 后会显示 `选择库存` 行级按钮
- **THEN** executor MUST 将 `物资信息` 解析为本次行按钮点击的表格作用域
- **AND** runtime MUST 只在 `wzxx_table` 对应的表格 root 内聚焦第 1 条业务行
- **AND** runtime MUST 点击 hover 后出现的 `选择库存` 行级按钮
- **AND** 步骤结果 MUST 包含 `action`、`row_number`、`table`，并在可用时包含 `table_fieldid`

#### Scenario: 在指定表格内按匹配条件点击行按钮
- **WHEN** DSL 文档执行 `table_row_action.click`
- **AND** `target.table` 指向一张可见表格
- **AND** `target.match.column` 和 `target.match.equals` 指向该表中的一条业务行
- **THEN** runtime MUST 将行匹配限定在目标表格作用域内
- **AND** runtime MUST NOT 在背景主表、其它子表或业务助手 iframe 中匹配同名文本行

#### Scenario: 紧邻可编辑表格录入后复用该表格作用域
- **WHEN** DSL 文档先成功执行 `editable_table.fill_row`
- **AND** 该步骤的 `target.table` 为 `物资信息`
- **AND** executor 已解析出 `table_fieldid=wzxx_table`
- **AND** 下一步立即执行 `table_row_action.click`
- **AND** 行按钮步骤未填写 `target.table`
- **AND** `target.action` 为 `选择库存`
- **AND** `target.row_number` 为 `1`
- **THEN** executor MUST 将前序 `物资信息` 可编辑表格作用域用于本次行按钮点击
- **AND** runtime MUST 只在 `wzxx_table` 对应的表格 root 内聚焦第 1 条业务行
- **AND** 步骤结果 MUST 包含实际使用的 `table` 和 `table_fieldid`

### Requirement: 未指定表格的行按钮保持兼容
系统 SHALL 保持未指定 `target.table` 的既有 `table_row_action.click` 行定位行为，避免破坏只有一张主表或目标行唯一的历史用例。

#### Scenario: 既有主表行按钮继续可用
- **WHEN** DSL 文档执行 `table_row_action.click`
- **AND** 未填写 `target.table`
- **AND** 前序步骤没有可消费的可编辑表格作用域
- **AND** `target.row_number` 为 `1`
- **AND** 当前页面只有一张可操作主表，目标行 hover 后存在目标行级按钮
- **THEN** executor MUST 保持既有未限定表格的行聚焦流程
- **AND** runtime MUST 点击目标行级按钮

#### Scenario: 显式表格失败时不回退全页面行
- **WHEN** DSL 文档执行 `table_row_action.click`
- **AND** `target.table` 为 `物资信息`
- **AND** 运行时无法在 `物资信息` 表格作用域内找到目标业务行
- **THEN** 步骤 MUST 失败
- **AND** runtime MUST NOT 回退到全页面第 N 行或其它表格中的同名行

### Requirement: 行按钮 DSL 校验接受表格作用域
系统 SHALL 将 `target.table` 和 `target.table_name` 识别为 `table_row_action.click` 的合法目标字段，但它们不能替代行定位字段。

#### Scenario: 接受表格和行号组合
- **WHEN** DSL 文档包含 `table_row_action.click`
- **AND** `target.action` 为 `选择库存`
- **AND** `target.table` 为 `物资信息`
- **AND** `target.row_number` 为 `1`
- **THEN** DSL validation MUST 接受该步骤

#### Scenario: 拒绝只有表格没有行定位
- **WHEN** DSL 文档包含 `table_row_action.click`
- **AND** `target.action` 为 `选择库存`
- **AND** `target.table` 为 `物资信息`
- **AND** 未填写 `target.match`、`target.row_number`、`target.row_numbers`、`target.row_index`、`target.first_available` 或 `target.select_first_available`
- **THEN** DSL validation MUST 在业务步骤执行前失败
- **AND** 错误信息 MUST 继续说明缺少行定位属性

### Requirement: 指定表格的行按钮诊断
系统 SHALL 在指定表格作用域的行级按钮点击失败时输出可判断根因的表格和行定位诊断。

#### Scenario: 找不到行时报告目标表格作用域
- **WHEN** `table_row_action.click` 指定了 `target.table`
- **AND** runtime 在目标表格作用域内未找到目标行
- **THEN** 错误信息 MUST 包含目标 `table`
- **AND** 如果 executor 已解析出表格身份，错误信息或步骤数据 MUST 包含 `table_fieldid`
- **AND** 诊断 SHALL 包含目标行号或匹配条件，以及目标表格可见行摘要或等价表格 root 摘要

#### Scenario: 找不到行按钮时保留动作诊断
- **WHEN** runtime 已在目标表格作用域内聚焦目标行
- **AND** hover 后未找到可点击的目标行级按钮
- **THEN** 步骤 MUST 失败为未找到可点击行级动作
- **AND** 错误信息 MUST 保留目标 `action`
- **AND** 诊断 SHOULD 包含当前可见行级动作候选摘要
