## ADDED Requirements

### Requirement: 参照型选择字段使用弹出参照语义
系统 SHALL 在 `form.fill` 处理表单字段时优先尊重模板 raw 元数据中的 `refuri` 参照声明，即使组件名是 `YDFSelect`，也不能仅因包含 `Select` 而归类为普通 choice 字段。

#### Scenario: YDFSelect 参照元数据打开弹出参照
- **WHEN** DSL 执行 `form.fill` 填写 `结算方式: "1 电子转账支付"`
- **AND** 当前模板字段组件名为 `YDFSelect`
- **AND** 字段 raw 元数据包含非空 `refuri` 参照定义
- **THEN** runtime MUST 将该字段作为 popup reference 字段处理
- **AND** runtime MUST NOT 把该字段交给普通 choice/dropdown 候选选择流程

### Requirement: 表单字段可见值已匹配时保持幂等
系统 SHALL 在 `form.fill` 打开普通 choice 或 popup reference 候选前，先检查当前字段可见值是否已经等价于 DSL 目标值；若已匹配，则该字段录入 MUST 成功且不得重复打开候选层。

#### Scenario: 默认参照选择值已经匹配
- **WHEN** DSL 执行 `form.fill` 填写 `结算方式: "1 电子转账支付"`
- **AND** 当前字段可见值已经是 `1 电子转账支付`
- **THEN** runtime MUST 将该字段录入判定为成功
- **AND** runtime MUST NOT 再打开普通下拉或 popup reference 候选
