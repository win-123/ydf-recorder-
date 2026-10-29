## ADDED Requirements

### Requirement: 按行号选择无 checkbox 行必须点击真实可接收事件的业务行
系统 SHALL 在 `table_row_selection.select` 使用 `target.row_number` 或 `target.first_available` 定位无 checkbox 业务行时，点击目标表格内真实可接收 pointer 事件的业务行区域；优先确认目标行进入真实选中/当前行状态，页面未暴露可读选中态时必须带出未确认但已点击真实业务行的诊断。

#### Scenario: 调出方无 checkbox 行点击后确认选中
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.table` 为 `调出方`
- **AND** `target.row_number` 为 `1`
- **AND** 目标表格第一条有效业务行没有可见 checkbox 或等效行选择控件
- **THEN** runtime MUST 在已解析的 `调出方` 表格作用域内点击可接收 pointer 事件的业务行单元格
- **AND** runtime MUST NOT 点击被表单、旧 DOM 或其它层覆盖的同文本行
- **AND** runtime SHOULD 在点击后确认目标行或等效当前行 DOM 出现真实选中证据
- **AND** 当页面未暴露可读选中证据但点击目标是真实可接收事件的业务行单元格时，步骤结果 MUST 包含 `accepted_unconfirmed=true`
- **AND** 步骤结果 MUST 包含 `row_numbers: [1]`、`table`、可用时的 `table_fieldid`，以及行点击诊断

#### Scenario: 行点击无法命中真实可接收业务行时失败
- **WHEN** runtime 已按行号找到目标业务行
- **AND** 该行没有可点击的行选择 checkbox 或等效行选择控件
- **AND** 该行或其对齐业务单元格无法通过 `elementFromPoint` 确认可接收 pointer 事件
- **THEN** `table_row_selection.select` MUST 失败
- **AND** 错误信息 MUST 说明未找到可选择的表格行
- **AND** 错误诊断 MUST 包含目标 `table`、可用时的 `table_fieldid`、行号和表格根摘要

#### Scenario: fieldid 命中旧表格根时按表名回退
- **WHEN** `target.table` 为 `调出方`
- **AND** runtime 已根据 `table_fieldid` 找到表格根
- **AND** 该表格根内不存在可接收 pointer 事件的有效业务行
- **THEN** runtime MUST 按 `target.table` 的可见标题重新解析表格根
- **AND** runtime MUST 支持 WUI 表头和表体分裂 DOM，将相邻 header/body 聚合为同一选择作用域

## MODIFIED Requirements

### Requirement: 按列值选择表格行
系统 SHALL 在 `table_row_selection.select` 使用 `target.match.column` 和 `target.match.equals` 时，按指定表格列的单元格值定位业务行，并在该行上执行行选择。

#### Scenario: 文本布尔列值可定位业务行
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.match.column` 为 `政府采购标识`
- **AND** `target.match.equals` 为 `是`
- **AND** 目标表格中存在一行的 `政府采购标识` 单元格显示文本为 `是`
- **THEN** runtime MUST 将该单元格值作为匹配依据定位业务行
- **AND** runtime MUST 点击同一业务行的行选择 checkbox、等效行选择控件，或在无选择控件时点击真实可接收 pointer 事件的业务行单元格并带出行点击诊断
- **AND** runtime MUST NOT 将 `政府采购标识` 这一文本单元格本身当作 checkbox

#### Scenario: 单值匹配不得退化为整行文本误选
- **WHEN** `table_row_selection.select` 的 `target.match.column` 为 `政府采购标识`
- **AND** `target.match.equals` 为 `是`
- **AND** 第一条可见数据行整行文本包含 `是`，但其 `政府采购标识` 单元格不是 `是`
- **THEN** runtime MUST NOT 选择该行
- **THEN** runtime MUST 继续查找 `政府采购标识` 单元格等于 `是` 的数据行

#### Scenario: 目标行存在但选择控件缺失时点击并验证业务行
- **WHEN** runtime 已按 `target.match.column` 和 `target.match.equals` 找到目标业务行
- **AND** 该行没有可点击的行选择 checkbox 或等效行选择控件
- **AND** 该行位于已解析的目标表格作用域内
- **THEN** runtime MUST 点击该目标业务行中真实可接收 pointer 事件的单元格以触发表格原生选中/高亮
- **AND** runtime SHOULD 在点击后确认目标行或等效当前行 DOM 出现真实选中证据；页面未暴露可读选中证据时 MUST 记录 `accepted_unconfirmed=true`
- **AND** runtime MUST NOT 退回全页面裸文本点击

### Requirement: 表格行选择的列归属作用域
系统 SHALL 在 `table_row_selection.select` 未显式指定 `target.table` 时，使用目标匹配列的表格归属限定选择作用域；无法唯一确定时必须在点击前失败。

#### Scenario: 目标列唯一归属于可用指标表
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** 未填写 `target.table`
- **AND** `target.match.column` 为 `政府采购标识`
- **AND** 当前模板中只有 `可用指标` 表包含 `政府采购标识` 列
- **THEN** executor MUST 将 `可用指标` 解析为本次行选择作用域
- **AND** executor MUST 在可用时向 runtime 传递该表的 `table_fieldid` 和列清单

#### Scenario: 多张表都包含目标列时拒绝歧义
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** 未填写 `target.table`
- **AND** 当前模板中多张可见主表都包含 `target.match.column`
- **THEN** 步骤 MUST 在点击任何行选择控件前失败
- **THEN** 错误信息 MUST 要求补充 `target.table`

#### Scenario: 目标行存在但点击后未选中时诊断清晰
- **WHEN** runtime 已按 `target.match.column` 和 `target.match.equals` 找到目标业务行
- **AND** 该行没有可点击的行选择 checkbox 或等效行选择控件
- **AND** runtime 点击该业务行后没有检测到真实选中/当前行证据
- **THEN** 步骤 MUST 失败
- **THEN** 错误信息 MUST 包含目标表格、目标列、匹配值，并说明未找到可选择的表格行或已点击业务行但未确认表格行选中

### Requirement: first_available 选择无 checkbox 的首条有效业务行
系统 SHALL 将 `table_row_selection.select target.first_available` 解释为选择目标表格内第一条有效业务行；当该行没有 checkbox 或等效行选择控件时，runtime MUST 在已解析表格作用域内点击该业务行，并在确认真实选中/当前行证据后返回成功。

#### Scenario: 目标表首条业务行没有 checkbox 时点击并验证行
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.table` 唯一指向一张可见主表格
- **AND** `target.first_available` 为 `true`
- **AND** 该表格第一条有效业务行没有可见 checkbox 或等效行选择控件
- **THEN** runtime MUST 点击该业务行
- **AND** runtime SHOULD 在点击后确认目标行或等效当前行 DOM 出现真实选中证据；页面未暴露可读选中证据时 MUST 记录 `accepted_unconfirmed=true`
- **AND** runtime MUST NOT 退回全页面裸文本点击
- **AND** 步骤结果 MUST 包含 `row_numbers: [1]`、`table`，并在可用时包含 `table_fieldid`

#### Scenario: 首条业务行存在 checkbox 时仍优先点击 checkbox
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.first_available` 为 `true`
- **AND** 第一条有效业务行包含可见 checkbox 或等效行选择控件
- **THEN** runtime MUST 优先点击该选择控件
- **AND** runtime MUST NOT 因新增行点击兜底而跳过选择控件

#### Scenario: first_available 忽略非业务行
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.first_available` 为 `true`
- **AND** 目标表格包含表头、`暂无数据` 占位行、小计行或合计行
- **THEN** runtime MUST NOT 将这些非业务行作为 first available 候选
- **AND** runtime MUST 继续查找第一条有效业务行

#### Scenario: 没有有效业务行时 first_available 失败
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.first_available` 为 `true`
- **AND** 已解析目标表格没有任何有效业务行
- **THEN** 步骤 MUST 失败
- **AND** 错误信息 MUST 说明未找到可选择的表格行号或未找到有效业务行，并包含目标表格诊断

#### Scenario: first_available 遵守多表格歧义规则
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.first_available` 为 `true`
- **AND** 未填写 `target.table`
- **AND** 当前页面存在多张可见主表格且无法唯一确定目标表格
- **THEN** 步骤 MUST 在点击任何行或选择控件前失败
- **AND** 错误信息 MUST 要求补充 `target.table`
