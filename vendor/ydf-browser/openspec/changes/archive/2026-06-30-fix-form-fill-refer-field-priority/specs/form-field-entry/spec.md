## MODIFIED Requirements

### Requirement: 前景表单字段绑定
系统 SHALL 在 `form.fill` 录入普通表单字段时优先绑定当前前景弹窗、抽屉或动态表单中的可见可编辑字段，避免同名或同 `fieldid` 的背景字段被误填。

#### Scenario: 前景弹窗字段优先于背景同 fieldid 字段
- **WHEN** 页面打开新增表单后，背景页和前景表单同时存在 `dataField=proCode` 或 `fieldid=proCode` 的字段
- **AND** DSL 执行 `form.fill` 填写 `项目代码`
- **THEN** runtime MUST 选择前景表单中可见、可编辑、非表格的 `项目代码` 控件
- **AND** runtime MUST NOT 将背景页、详情区或列表区的同名字段作为录入目标

#### Scenario: 前景字段按标签或身份匹配
- **WHEN** 前景表单字段没有稳定 `fieldid`，但其 `label_text`、`aria_label`、`placeholder`、`dataField` 或模板 key 能匹配 DSL 字段名
- **THEN** runtime MUST 允许该前景字段作为 `form.fill` 目标
- **AND** runtime MUST 在存在多个候选时优先选择可编辑字段而不是只读展示字段

#### Scenario: 同名展示字段不得抢占可编辑参照字段
- **WHEN** 前景动态表单中同时存在两个标签均为 `采购品目` 的字段
- **AND** 其中一个候选是 `props.disabled=1` 的 `YDFInput` 展示字段
- **AND** 另一个候选是可编辑的 `YDFTableModalSelect` 或 `dataType=refer` 字段
- **AND** DSL 执行 `form.fill`，为 `采购品目` 提供包含 `filter` 和 `match` 的结构化参照目标
- **THEN** runtime MUST 选择可编辑参照字段作为录入目标
- **AND** runtime MUST NOT 将 disabled 展示字段作为当前 `form.fill` 的候选
- **AND** runtime MUST NOT 把结构化参照目标交给普通 choice/dropdown 选择逻辑
