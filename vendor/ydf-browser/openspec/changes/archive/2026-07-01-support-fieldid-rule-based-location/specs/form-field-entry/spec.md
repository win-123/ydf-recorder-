## ADDED Requirements

### Requirement: 表单字段绑定使用规则推导身份
系统 SHALL 在 `form.fill` 绑定普通表单字段时，优先使用 YonDiF `父容器 divCode + "_" + dataField` 及组件子控件后缀规则生成的运行时 `fieldid` 候选。

#### Scenario: 普通输入字段使用父容器规则定位
- **WHEN** 模板中 `YDFInput` 字段标签为 `项目名称`，`dataField=proName`，所属表单容器 `divCode=baseForm`
- **THEN** binder MUST 优先尝试运行时身份 `baseForm_proName`
- **AND** 如果该候选可见、可编辑且位于当前前景表单，`form.fill` MUST 使用该候选录入

#### Scenario: 参照字段使用子控件后缀定位
- **WHEN** 模板中表单字段组件为 `YDFTableModalSelect` 或 `YDFTreeModalSelect`
- **AND** 字段 `dataField=depart`，所属表单容器 `divCode=baseForm`
- **THEN** runtime MUST 可使用 `baseForm_depart_input`、`baseForm_depart_btn`、`baseForm_depart_table`、`baseForm_depart_tree`、`baseForm_depart_modal_ok` 和 `baseForm_depart_modal_cancel` 定位参照输入、按钮、弹层和确认动作
- **AND** runtime MUST 继续按现有参照选择语义确认回填值
