## ADDED Requirements

### Requirement: 可编辑表格字段支持父表头限定
系统 SHALL 允许 `editable_table.fill_row` 的字段声明携带父表头限定，用于在同一目标表格内区分同名明细列。

#### Scenario: 对象字段值声明父表头
- **WHEN** DSL 文档执行 `editable_table.fill_row`
- **AND** `target.fields` 使用对象写法，字段 `当年财政拨款(万元)` 的值为包含 `column_group: 全年执行决算金额` 和 `value: 3` 的对象
- **THEN** 系统 MUST 将 `当年财政拨款(万元)` 作为叶子列名
- **AND** 系统 MUST 将 `全年执行决算金额` 作为该字段的父表头限定
- **AND** 系统 MUST 将 `3` 作为实际录入值

#### Scenario: 普通字段和父表头字段混合录入
- **WHEN** DSL 文档在同一个 `editable_table.fill_row` 步骤中同时包含普通字段 `备注: 测试` 和字段值包装器 `当年财政拨款(万元): {column_group: 全年执行决算金额, value: 3}`
- **THEN** 系统 MUST 保持 `备注` 的既有普通列定位和录入语义
- **AND** 系统 MUST 仅对 `当年财政拨款(万元)` 应用父表头限定

#### Scenario: 父表头字段包装结构化参照值
- **WHEN** DSL 文档执行 `editable_table.fill_row`
- **AND** 字段 `项目目录` 的值包含 `column_group: 项目信息`
- **AND** 字段真实值位于 `value` 中，且 `value` 包含 `tree`、`match` 或 `first_available` 等结构化参照目标
- **THEN** 系统 MUST 使用 `column_group` 定位目标列
- **AND** 系统 MUST 将 `value` 内的对象按既有结构化参照目标处理
- **AND** 系统 MUST NOT 将字段包装器整体字符串化写入单元格

#### Scenario: 列表字段项声明父表头
- **WHEN** DSL 文档执行 `editable_table.fill_row`
- **AND** `target.fields` 使用列表写法，某项包含 `field: 当年财政拨款(万元)`、`column_group: 全年执行决算金额` 和 `equals: 3`
- **THEN** 系统 MUST 将该列表项解释为叶子列 `当年财政拨款(万元)` 在父表头 `全年执行决算金额` 下录入 `3`

### Requirement: 父表头限定支持多级路径
系统 SHALL 支持 `column_group` 使用字符串或字符串列表表达父表头限定；列表形式 MUST 从外层父表头到内层父表头匹配，不包含叶子列名。

#### Scenario: 单级父表头字符串
- **WHEN** DSL 文档中字段包装器包含 `column_group: 全年执行决算金额`
- **THEN** 系统 MUST 将其归一化为父表头路径 `["全年执行决算金额"]`

#### Scenario: 多级父表头列表
- **WHEN** DSL 文档中字段包装器包含 `column_group: [资金金额, 全年执行决算金额]`
- **THEN** 系统 MUST 按 `资金金额` 到 `全年执行决算金额` 的顺序匹配目标列的父表头路径
- **AND** 系统 MUST NOT 要求列表中重复包含叶子列名

### Requirement: 同名明细列必须可判定或失败
系统 MUST 在 `editable_table.fill_row` 解析目标列时避免对同名明细列做隐式猜测；如果无法根据叶子列名、目标表格和父表头限定唯一确定目标列，当前步骤 MUST 失败。

#### Scenario: 同名列未提供父表头限定
- **WHEN** 目标表格中存在多个叶子列名均为 `当年财政拨款(万元)` 的可见或可绑定列
- **AND** DSL 文档只写 `fields: {当年财政拨款(万元): 3}`，未提供 `column_group`
- **THEN** 当前 `editable_table.fill_row` 步骤 MUST 失败
- **AND** 错误信息 MUST 包含目标叶子列名和可用父表头路径摘要
- **AND** 系统 MUST NOT 默认写入第一个同名列

#### Scenario: 父表头限定后唯一命中
- **WHEN** 目标表格中存在 `全年执行自评金额 > 当年财政拨款(万元)` 和 `全年执行决算金额 > 当年财政拨款(万元)` 两个叶子列
- **AND** DSL 文档为字段 `当年财政拨款(万元)` 提供 `column_group: 全年执行决算金额`
- **THEN** 系统 MUST 选择 `全年执行决算金额 > 当年财政拨款(万元)` 对应的模板列身份或 DOM 单元格
- **AND** 系统 MUST NOT 写入 `全年执行自评金额 > 当年财政拨款(万元)` 对应单元格

#### Scenario: 父表头限定仍不唯一
- **WHEN** 目标表格中多个候选列都匹配叶子列名和 `column_group`
- **THEN** 当前字段 MUST 失败
- **AND** 错误信息 MUST 包含所有冲突候选的父表头路径和可用列身份摘要

### Requirement: 父表头定位诊断可追踪
系统 SHALL 在父表头限定参与 `editable_table.fill_row` 定位时，在成功或失败诊断中暴露目标父表头路径、实际命中列身份和定位来源。

#### Scenario: 成功报告父表头路径
- **WHEN** `editable_table.fill_row` 成功录入带 `column_group` 的字段
- **THEN** 字段级结果 SHALL 保留原有 `column`、`value`、`fieldid`、`data_field` 和 `table_fieldid`
- **AND** 字段级结果 SHALL 包含目标父表头路径或等价诊断字段
- **AND** 字段级结果 SHALL 包含实际定位来源，例如模板身份、DOM 多表头几何兜底或现有身份单元格定位来源

#### Scenario: DOM 多表头兜底报告候选路径
- **WHEN** 模板中无法解析目标列父表头路径
- **AND** runtime 通过真实 DOM 多行表头几何关系完成目标列定位
- **THEN** 字段级结果 SHALL 标记该字段使用 DOM 表头路径兜底
- **AND** 失败诊断 MUST 包含当前目标表格内可识别的表头路径摘要
