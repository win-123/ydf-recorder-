## ADDED Requirements

### Requirement: 表格行选择全选目标
系统 SHALL 允许 `table_row_selection.select` 通过设置 `target.select_all: true` 点击表格组件表头 checkbox，以选择该表格组件原生暴露的全部行。

#### Scenario: 单个可见表格中选择全部行
- **WHEN** 测试集执行 `table_row_selection.select`，且 `target.select_all` 为 `true`，当前页面只有一张可见主表格
- **THEN** executor MUST 将这张表格解析为选择作用域
- **THEN** runtime MUST 在表头 checkbox 尚未完全选中时点击该 checkbox
- **THEN** 步骤结果 MUST 包含 `select_all: true`

#### Scenario: 指定表格中选择全部行
- **WHEN** 测试集执行 `table_row_selection.select`，且 `target.table` 为一张可见主表格名称、`target.select_all` 为 `true`
- **THEN** executor MUST 使用现有表格作用域规则解析匹配表格的 `fieldid`
- **THEN** runtime MUST 将表头 checkbox 查找和点击限定在该表格作用域内
- **THEN** 步骤结果 MUST 包含 `select_all: true`、`table`，并在可用时包含解析出的 `table_fieldid`

#### Scenario: 多张可见表格时拒绝歧义全选
- **WHEN** 测试集执行 `table_row_selection.select`，且 `target.select_all` 为 `true`、未填写 `target.table`，当前页面存在多张可见主表格
- **THEN** 步骤 MUST 在点击任何 checkbox 前失败
- **THEN** 错误信息 MUST 说明当前页面包含多张表格，并要求补充 `target.table`

### Requirement: 表头 Checkbox 定位
系统 SHALL 在执行 `target.select_all` 时只定位已解析表格的表头 checkbox。

#### Scenario: 忽略数据行 Checkbox
- **WHEN** 已解析表格的表头行和数据行都包含 checkbox 控件
- **THEN** runtime MUST 点击表头区域内的 checkbox 控件
- **THEN** runtime MUST NOT 将 `tbody` 数据行 checkbox 作为全选目标

#### Scenario: 表头 Checkbox 不可用时失败
- **WHEN** 测试集执行 `table_row_selection.select`，且 `target.select_all` 为 `true`，已解析表格有可选择数据行但没有可见表头 checkbox
- **THEN** 步骤 MUST 失败
- **THEN** 错误信息 MUST 标识未找到表头全选 checkbox

#### Scenario: 已选中表头 Checkbox 保持选中
- **WHEN** 已解析表格的表头 checkbox 已处于完全选中状态
- **THEN** runtime MUST 将本次全选操作视为成功
- **THEN** runtime MUST NOT 以会导致全部行反选的方式点击 checkbox

#### Scenario: 点击半选或未选中的表头 Checkbox
- **WHEN** 已解析表格的表头 checkbox 处于未选中或半选状态
- **THEN** runtime MUST 点击表头 checkbox 或其可点击 wrapper
- **THEN** runtime MUST 等待表格选择状态稳定后再返回成功

### Requirement: 全选 DSL 校验
系统 SHALL 将 `target.select_all` 校验为互斥的表格行选择定位方式。

#### Scenario: 接受全选目标
- **WHEN** DSL 文档包含 `table_row_selection.select`，且 `target.select_all` 为 `true`
- **THEN** DSL validation MUST 接受该步骤，且不要求填写 `target.match`、`target.rows`、`target.row_number` 或 `target.first_available`

#### Scenario: 拒绝全选与行定位混用
- **WHEN** DSL 文档包含 `table_row_selection.select`，且 `target.select_all` 为 `true`，同时还包含 `target.match`、`target.rows`、`target.row_number`、`target.row_numbers`、`target.row_index`、`target.first_available` 或 `target.select_first_available` 中任一字段
- **THEN** DSL validation MUST 在业务步骤执行前失败
- **THEN** 错误信息 MUST 说明 `target.select_all` 不能与行定位目标混用
