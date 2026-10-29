## ADDED Requirements

### Requirement: 普通文本域不得由弱参照装饰改写语义
系统 SHALL 将没有明确参照组件身份或模板 `refuri` 等参照元数据的 `YDFTextArea` 作为普通文本字段处理；祖先容器中的搜索、箭头、选择或相似视觉装饰 MUST NOT 单独使文本域进入弹出参照流程。

#### Scenario: 带搜索装饰的备注仍按文本录入
- **WHEN** DSL 执行 `form.fill` 填写 `YDFTextArea` 字段 `备注`
- **AND** 该字段没有明确参照组件身份或模板参照元数据
- **AND** 字段祖先容器中存在搜索、箭头或选择装饰
- **THEN** 系统 MUST 按普通文本录入并确认字段回填
- **AND** 系统 MUST NOT 打开弹出参照候选层

#### Scenario: 明确参照文本域保持参照语义
- **WHEN** DSL 执行 `form.fill` 填写 `YDFTextArea` 字段
- **AND** 该字段模板具有明确参照组件身份或非空 `refuri` 参照元数据
- **THEN** 系统 MUST 保持既有弹出参照选择和回填确认语义
