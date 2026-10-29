## ADDED Requirements

### Requirement: 可编辑表格单元格限定到前景目标表格
系统 MUST 在执行 `editable_table.fill_row` 定位单元格时，将行和单元格搜索限定到当前前景可操作的目标可编辑表格；背景列表、旧模板残留表格、业务助手 iframe、非目标表格或被遮挡表格不得参与目标行选择。

#### Scenario: 连续运行后不串到上一轮待提交列表行
- **WHEN** DSL 文档执行 `editable_table.fill_row`，目标表格为 `物资信息`，`row_number: -1`
- **AND** 当前新增页前景包含 `物资信息` 可编辑子表，子表中有一条已通过 `物资分类` 参照回填的行
- **AND** 页面 DOM 中仍存在上一轮保存出的待提交列表行，例如包含 `LY202600000001` 和旧申请事由
- **THEN** 系统 MUST 在前景 `物资信息` 子表内解析 `row_number: -1`
- **AND** 系统 MUST 激活该子表行的 `申请数量` 单元格
- **AND** 系统 MUST NOT 将背景待提交列表行作为 `editable_table.fill_row` 的目标行

#### Scenario: 目标表格 root 为空时当前字段失败
- **WHEN** DSL 文档执行 `editable_table.fill_row`，且目标表格名或模板列身份能解析出目标 `tableFieldid`
- **AND** 运行时找不到当前前景可操作的目标表格 root 或目标 root 内没有可编辑数据行
- **THEN** 当前 `editable_table.fill_row` 步骤 MUST 在当前字段失败
- **AND** 错误信息 MUST 包含目标表格名、目标 `tableFieldid`、候选 root 摘要和可见表格诊断
- **AND** 系统 MUST NOT 继续扫描背景列表或其他表格并把其中的行当作目标行

### Requirement: 可编辑表格串表诊断
系统 SHALL 在可编辑表格单元格定位失败或编辑器缺失时输出足够诊断，用于区分目标子表无编辑器、目标 root 未找到、命中背景列表行和业务数据缺失。

#### Scenario: 编辑器缺失时报告实际命中的 root 和 row
- **WHEN** `editable_table.fill_row` 已定位到某个候选单元格
- **AND** 激活该单元格后没有出现可输入控件
- **THEN** 错误信息 SHALL 包含目标表格名、目标列名、目标 `tableFieldid`、定位来源、候选 root 摘要、被选中 row 文本和 row index
- **AND** 如果候选 row 文本不属于目标前景表格，诊断 SHOULD 能体现该 row 来自背景或非目标表格

#### Scenario: 成功录入时保留目标表格定位诊断
- **WHEN** `editable_table.fill_row` 成功录入普通文本列、数字列或结构化参照列
- **THEN** 字段级结果 SHALL 保留既有列身份信息，例如 `fieldid`、`data_field`、`table_fieldid` 和 `locator_source`
- **AND** 字段级结果 SHALL 包含足以判断目标 root 的诊断字段，例如 root 来源、目标表格身份或等价摘要
- **AND** 普通文本和数字列录入行为 MUST 保持既有语义
