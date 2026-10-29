# query-popup-reference-selection Specification

## Purpose

定义 `query.search` 在查询条件字段为 YonDiF 弹出参照控件时的选择、值传递和结果报告行为，确保查询参照与表单参照复用一致的语义，同时保持普通文本、下拉和树形下拉查询条件兼容。
## Requirements
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

### Requirement: 普通枚举查询条件保持下拉行为
系统 SHALL 在 `query.search` 中将普通枚举查询字段识别为 choice/dropdown 字段，并使用普通下拉候选选择流程录入查询值。

#### Scenario: 单据类型查询选择调拨
- **WHEN** 用例在 `query.search` 中填写 `单据类型 = 调拨`
- **AND** 当前查询字段模板组件为 `LCDEnum` 或 raw 元数据包含非空 `enumType`
- **AND** 该字段未声明为 modal/reference 参照字段
- **THEN** 运行时 MUST 使用普通 choice/dropdown 候选选择逻辑选择 `调拨`
- **AND** 运行时 MUST NOT 调用弹出参照选择流程
- **AND** 运行时 MUST NOT 报告 `未打开弹出参照选择框`
- **AND** 如果页面未将查询字段提交为 `调拨`，运行时 MUST 让该步骤失败并报告 choice/dropdown 诊断

### Requirement: 查询区和查询参照使用规则推导身份
系统 SHALL 在 `query.search` 和查询弹出参照中，使用 `LCDQueryString` 容器编码及查询字段父容器规则推导查询输入、查询按钮、模糊查询和参照子控件身份。

#### Scenario: 查询按钮和模糊查询使用 query divCode
- **WHEN** 模板中查询区 `divCode=dataQueryArea`
- **THEN** runtime MUST 优先尝试 `dataQueryArea_query_icon` 作为执行查询按钮候选
- **AND** runtime MUST 可使用 `dataQueryArea_fuzzy_input`、`dataQueryArea_fuzzy_btn` 和 `dataQueryArea_fuzzy_icon` 定位模糊查询控件

#### Scenario: 查询参照字段使用 modal suffixes
- **WHEN** 查询条件字段组件为 `YDFTableModalSelect` 或 `YDFTreeModalSelect`
- **AND** 字段所属查询区 `divCode=dataQueryArea` 且 `dataField=depart`
- **THEN** runtime MUST 可使用 `dataQueryArea_depart_input`、`dataQueryArea_depart_btn`、`dataQueryArea_depart_table`、`dataQueryArea_depart_tree`、`dataQueryArea_depart_modal_ok` 和 `dataQueryArea_depart_modal_cancel` 定位参照交互
- **AND** runtime MUST 继续将候选选择限定在当前可见参照弹层内

### Requirement: 查询动作重新绑定延迟出现的 manifest 字段
当当前页面 manifest 明确声明目标查询字段，但该字段在最近一次 binding 中尚未命中时，系统 SHALL 在报告字段未绑定前限时刷新当前 manifest 的运行时 binding；刷新命中后 MUST 使用该查询字段继续执行查询。

#### Scenario: 查询输入在页签绑定快照后出现
- **WHEN** `tab.click` 已完成且当前 manifest 声明查询字段“专家姓名”
- **AND** 页签步骤结束时的 binding 尚未包含该字段
- **AND** 运行时随后渲染出该查询输入
- **THEN** 紧接的 `query.search` MUST 刷新当前 manifest binding 并绑定“专家姓名”
- **AND** 查询 MUST NOT 因页签步骤的一次旧 binding 快照而报告“未绑定查询字段”

#### Scenario: 不把编辑表单字段当作查询字段
- **WHEN** `query.search` 请求的字段不属于当前 manifest 的查询字段
- **AND** 当前 manifest 声明保存、提交或取消等稳定编辑动作
- **THEN** 系统 MUST 报告该查询字段未绑定
- **AND** 系统 MUST NOT 将运行时同名普通表单字段作为查询字段兜底
