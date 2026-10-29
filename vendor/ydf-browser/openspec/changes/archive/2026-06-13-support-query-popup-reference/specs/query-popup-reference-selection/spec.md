## ADDED Requirements

### Requirement: Query search supports popup reference fields
系统 SHALL 在 `query.search` 中识别查询条件字段的弹出参照控件，并用弹出参照选择流程录入查询值。

#### Scenario: 查询条件项目目录使用树形弹出参照
- **WHEN** 用例在 `query.search` 中填写 `项目目录 = 101 财政一级`，且该查询字段模板组件为 `YDFTreeModalSelect` 或元数据声明为 refer/modal 参照
- **THEN** 运行时 MUST 打开该查询字段的弹出参照，在当前参照弹窗内选择 `101 财政一级`，确认或等待参照回填，然后点击真实查询按钮
- **AND** 运行时 MUST NOT 将该字段交给普通 dropdown 或树形下拉候选选择逻辑

#### Scenario: 普通树形下拉查询条件保持原行为
- **WHEN** 用例在 `query.search` 中填写普通 `YDFTreeSelect` 查询字段，例如 `项目申报部门 = 001 办公室`
- **THEN** 运行时 SHALL 继续使用现有查询下拉/树形下拉选择逻辑
- **AND** 运行时 MUST NOT 因字段组件名包含 `TreeSelect` 就打开弹出参照流程

### Requirement: Query popup reference conditions preserve structured values
系统 MUST 保留 `query.search target.conditions[].equals` 的原始值类型，使列表和结构化参照目标能够进入运行时弹出参照选择流程。

#### Scenario: 查询条件弹出参照支持多选列表
- **WHEN** 用例将弹出参照查询字段填写为 `equals` 列表，例如 `["101 财政一级", "767 财务一级测试"]`
- **THEN** 执行器 MUST 将该列表原样传给查询字段填值运行时
- **AND** 运行时 MUST 按弹出参照多选语义选择列表中的每个目标，而不是把列表转换成字符串后填入或按 dropdown 文本查找

#### Scenario: 查询条件弹出参照支持结构化目标
- **WHEN** 用例将弹出参照查询字段填写为包含 `value`、`values`、`match`、`matches`、`row_number`、`first_available`、`selections` 或 `tree` 的结构化 `equals`
- **THEN** 执行器 MUST 保留该结构化目标并传给运行时
- **AND** 运行时 MUST 使用与表单字段弹出参照一致的语义选择候选

#### Scenario: 表格型查询参照要求结构化匹配
- **WHEN** 查询字段模板组件为 `YDFTableModalSelect`
- **THEN** 系统 MUST 要求该字段使用有效的结构化表格匹配目标，例如 `match`、`row_number` 或 `first_available`
- **AND** 系统 MUST NOT 按标量文本直接尝试选择表格型参照候选

### Requirement: Query search reports popup reference diagnostics
系统 SHALL 在 `query.search` 步骤结果中报告查询条件弹出参照的选择诊断。

#### Scenario: 报告弹出参照选择结果
- **WHEN** 查询条件字段通过弹出参照流程完成选择
- **THEN** 步骤结果中对应条件 MUST 包含原始 `field` 和 `equals`
- **AND** 如果运行时返回了 `selected`、`confirmed`、`confirm_label` 或 `popup_tree_context`，步骤结果 MUST 将这些信息记录在该条件结果中

#### Scenario: 普通查询条件报告保持兼容
- **WHEN** 查询条件字段是文本框、普通下拉或普通树形下拉
- **THEN** 步骤结果 SHALL 继续记录 `field` 和 `equals`
- **AND** 不存在弹出参照诊断时，步骤结果 MUST NOT 添加空的 `selected`、`confirmed`、`confirm_label` 或 `popup_tree_context`
