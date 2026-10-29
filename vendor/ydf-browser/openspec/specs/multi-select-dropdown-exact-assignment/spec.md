# multi-select-dropdown-exact-assignment Specification

## Purpose
定义普通多选下拉按最终目标集合精确赋值、候选身份匹配、结果校验、错误报告和单选或弹出参照边界的运行时语义。
## Requirements
### Requirement: 普通多选下拉使用精确目标集合赋值
系统 SHALL 将查询区、表单和可编辑表格中的普通多选下拉录入解释为最终目标集合赋值，而不是在页面已有选中项上追加目标。

#### Scenario: 查询标量值替换默认选中项
- **WHEN** `query.search` 为普通多选下拉字段填写标量值 `草稿`
- **AND** 页面初始已选集合为 `启用`
- **THEN** 运行时 MUST 将标量规范化为目标集合 `{草稿}`
- **AND** 最终已选集合 MUST 只包含 `草稿`
- **AND** 运行时 MUST NOT 保留 DSL 未声明的 `启用`

#### Scenario: 列表值是无序精确集合
- **WHEN** `form.fill` 或 `editable_table.fill_row` 为普通多选下拉字段填写列表 `[草稿, 启用]`
- **THEN** 运行时 MUST 将列表视为无序目标集合
- **AND** `[启用, 草稿]` MUST 与该目标集合等价
- **AND** 最终已选集合 MUST 不包含目标集合之外的项目

#### Scenario: 空列表清空全部选中项
- **WHEN** 任一支持的普通多选下拉录入入口填写空列表 `[]`
- **THEN** 运行时 MUST 清空该字段的全部已选项
- **AND** 最终已选集合 MUST 为空

### Requirement: 多选目标拒绝重复值
系统 MUST 将普通多选下拉目标列表中的重复值视为 DSL 输入错误，不得静默去重后继续执行。

#### Scenario: 重复值导致校验失败
- **WHEN** 多选目标列表为 `[草稿, 草稿]`
- **THEN** DSL 校验或绑定后的组件语义校验 MUST 失败
- **AND** 错误信息 MUST 指出目标列表包含重复值
- **AND** 运行时 MUST NOT 以单元素集合继续录入

### Requirement: 多选赋值使用唯一候选项身份
系统 SHALL 按唯一候选项身份匹配多选目标和最终已选项，允许编码、名称和空白等显示格式差异，但不得接受歧义候选。

#### Scenario: 编码和名称显示差异仍标识同一候选项
- **WHEN** DSL 目标为 `001 办公室`
- **AND** 当前候选项可唯一确定为同一业务项，但选中标签只显示 `办公室`
- **THEN** 运行时 MUST 将两者视为同一候选项身份
- **AND** 最终集合校验 MUST NOT 因显示格式差异失败

#### Scenario: 候选项身份歧义时失败
- **WHEN** 一个 DSL 目标同时匹配多个可见候选项
- **THEN** 运行时 MUST 让当前字段录入失败
- **AND** 运行时 MUST NOT 通过模糊文本任选一个候选项

### Requirement: 多选赋值校验并报告完整最终集合
系统 MUST 在录入后重新读取普通多选下拉的完整已选集合，并在结构化报告中记录目标集合与实际集合。

#### Scenario: 成功赋值报告目标值和实际值
- **WHEN** 普通多选下拉最终实际集合与目标集合按候选项身份等价
- **THEN** 当前字段录入 SHALL 成功
- **AND** 报告 MUST 包含 `expected_values` 和 `actual_values`
- **AND** 两个集合 MUST 在忽略顺序后等价

#### Scenario: 缺项或额外项导致赋值失败
- **WHEN** 普通多选下拉最终实际集合存在目标缺项或额外项
- **THEN** 当前字段录入 MUST 失败
- **AND** 报告 MUST 包含 `expected_values`、`actual_values`、`missing_values` 和 `unexpected_values`
- **AND** 运行时 MUST NOT 仅因某个目标文本已经出现就报告成功

### Requirement: 精确赋值仅适用于普通多选下拉
系统 MUST 将本能力限定在运行时呈现为普通多选候选面的字段，并保持普通单选下拉与弹出参照的既有语义。

#### Scenario: 单选下拉保持既有行为
- **WHEN** 查询区、表单或可编辑表格字段在模板和运行时中均表现为普通单选下拉
- **THEN** 运行时 SHALL 继续使用既有单目标 choice/dropdown 选择流程
- **AND** 运行时 MUST NOT 要求该字段执行多选集合同步

#### Scenario: 弹出参照多选不在范围内
- **WHEN** 字段为 `YDFTreeModalSelect`、`YDFTableModalSelect` 或其它需要弹窗确认的弹出参照
- **THEN** 运行时 SHALL 继续使用弹出参照的列表、`selections` 和确认语义
- **AND** 运行时 MUST NOT 将该字段交给普通多选下拉精确赋值流程
