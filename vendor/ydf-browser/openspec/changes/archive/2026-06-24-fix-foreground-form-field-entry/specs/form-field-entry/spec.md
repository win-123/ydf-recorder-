## ADDED Requirements

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

### Requirement: 表单字段录入确认
系统 SHALL 在普通表单字段录入后确认目标控件真实回填了 DSL 目标值；未确认时该字段录入 MUST 失败。

#### Scenario: 文本字段未回填时失败
- **WHEN** DSL 执行 `form.fill` 填写普通文本字段
- **AND** runtime 已向目标控件发送输入事件
- **AND** 目标控件在短等待内仍读不到 DSL 目标值
- **THEN** `form.fill` MUST 失败
- **AND** 失败诊断 MUST 包含字段名、目标值、实际读数和运行时 selector

#### Scenario: 年份日期字段确认写入
- **WHEN** DSL 执行 `form.fill` 填写 `YDFDatePicker` 年份字段，例如 `设立年度: "2026"`
- **THEN** runtime MUST 以该字段的真实可编辑控件为目标写入年份
- **AND** runtime MUST 确认字段可见值或 input value 等价于 `2026`

#### Scenario: 成功报告包含确认后的字段
- **WHEN** `form.fill` 完成多个字段录入
- **THEN** 步骤结果 MUST 只把已经确认回填的普通字段报告为成功录入
- **AND** 报告 MUST 包含每个字段的 `fieldid` 或等价运行时身份，便于诊断绑定位置
