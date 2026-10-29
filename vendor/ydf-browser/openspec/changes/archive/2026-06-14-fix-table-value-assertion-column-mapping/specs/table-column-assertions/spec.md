## ADDED Requirements

### Requirement: 表格列值断言使用目标表格作用域
系统 SHALL 在执行 `table.assert_column_values` 时将列值采集限定在目标表格作用域内，并使用目标表格的真实表头定位列。

#### Scenario: 指定表格后采集该表格列值
- **WHEN** DSL 文档执行 `table.assert_column_values`，且 `target.table` 指向当前模板中的目标表格
- **THEN** executor MUST 将 `target.table` 解析为目标表格作用域
- **THEN** runtime MUST 只在该表格作用域内采集 `target.column` 的单元格值
- **AND** runtime MUST NOT 使用全页面其它表格或表单区域中的同名/近似列作为采集来源

#### Scenario: 未指定表格时按目标列推断唯一表格
- **WHEN** DSL 文档执行 `table.assert_column_values`，未填写 `target.table`
- **AND** 当前模板只有一个可见主表格包含 `target.column`
- **THEN** executor MUST 将该表格作为目标表格作用域
- **THEN** runtime MUST 在该表格作用域内采集列值

#### Scenario: 多表格无法唯一推断时失败
- **WHEN** DSL 文档执行 `table.assert_column_values`，未填写 `target.table`
- **AND** 当前页面存在多张可见主表格，且无法根据 `target.column` 唯一确定目标表格
- **THEN** 步骤 MUST 在采集单元格值前失败
- **AND** 错误信息 MUST 要求补充 `target.table` 或更明确的目标上下文

### Requirement: 表格行值断言按业务行和列身份读取字段
系统 SHALL 在执行 `table.assert_row_values` 时先在目标表格内定位业务行，再按同一表格的列身份读取该行字段值。

#### Scenario: 按匹配列定位行并读取目标列
- **WHEN** DSL 文档执行 `table.assert_row_values`
- **AND** `target.match.column` 为 `被授权人名称`、`target.match.equals` 为 `人员二十二`
- **AND** `target.fields` 包含 `可授权金额: "400.00"`
- **THEN** runtime MUST 在目标表格内找到 `被授权人名称 = 人员二十二` 的业务行
- **THEN** runtime MUST 从该业务行的 `可授权金额` 列读取实际值
- **AND** 只有该实际值匹配 `400.00` 时步骤 MUST 成功

#### Scenario: 多条件匹配使用列值而不是整行裸文本
- **WHEN** DSL 文档执行 `table.assert_row_values`，且 `target.match.conditions` 包含多个列条件
- **THEN** runtime MUST 按每个条件的列名读取候选行对应列值
- **AND** runtime MUST 只在所有条件列值均匹配时选择该业务行

#### Scenario: 目标行存在但字段列缺失时失败
- **WHEN** DSL 文档执行 `table.assert_row_values`
- **AND** runtime 已找到匹配业务行
- **AND** 目标表格表头不包含 `target.fields` 中的任一字段列
- **THEN** 步骤 MUST 失败
- **AND** 错误信息 MUST 标识缺失字段列和当前目标表格 headers

### Requirement: 表格数据值断言使用稳定列映射
系统 SHALL 使用稳定列映射读取 `table.assert_column_values` 和 `table.assert_row_values` 的单元格值，避免相邻列、固定列副本或其它表格串列。

#### Scenario: 相邻列不得串读
- **WHEN** 目标表格同时包含 `可授权金额`、`起始时间`、`项目名称` 等相邻列
- **THEN** 断言 `可授权金额` 时 runtime MUST 读取 `可授权金额` 列的单元格
- **AND** runtime MUST NOT 将 `起始时间`、`项目名称` 或其它相邻列的值作为 `可授权金额` 的实际值

#### Scenario: header 和 body 分离渲染仍能对齐
- **WHEN** YonDiF 表格将 header 和 body 分离渲染，或存在固定列副本
- **THEN** runtime MUST 优先使用列 identity、表头 identity、dataField、fieldid 或等效 DOM 属性对齐 header 和 body 单元格
- **AND** 只有缺少 identity 时才能在目标表格范围内使用列索引或几何对齐兜底

#### Scenario: 失败诊断包含表格和值采集上下文
- **WHEN** 数据值断言因列缺失、行缺失、值不匹配或无法唯一确定表格而失败
- **THEN** 错误诊断 MUST 包含可用时的 `table`、`table_fieldid`、目标列、匹配条件和目标表格 headers
- **AND** 错误诊断 MUST NOT 只返回其它列的误采值作为失败依据

### Requirement: 表格数据值断言 DSL 支持可选表格作用域
系统 SHALL 允许 `table.assert_column_values` 和 `table.assert_row_values` 在 target 中使用可选表格作用域字段，以便多表格页面明确断言目标。

#### Scenario: 接受列值断言的表格作用域字段
- **WHEN** DSL 文档包含 `table.assert_column_values`，且 target 中包含 `table` 或 `table_name`
- **THEN** DSL validation MUST 接受该步骤
- **AND** executor MUST 将该字段用于目标表格作用域解析

#### Scenario: 接受行值断言的表格作用域字段
- **WHEN** DSL 文档包含 `table.assert_row_values`，且 target 中包含 `table` 或 `table_name`
- **THEN** DSL validation MUST 接受该步骤
- **AND** executor MUST 将该字段用于目标表格作用域解析

#### Scenario: 显式表格作用域可使用运行时 fieldid
- **WHEN** DSL 文档包含 `table.assert_row_values` 或 `table.assert_column_values`
- **AND** `target.table` 填写的是当前 DOM 中可见表格的 fieldid
- **AND** 当前动态模板 manifest 未包含该 fieldid
- **THEN** executor MUST NOT 在采集前报表格名称未匹配
- **AND** runtime MUST 使用该 fieldid 限定目标表格作用域
