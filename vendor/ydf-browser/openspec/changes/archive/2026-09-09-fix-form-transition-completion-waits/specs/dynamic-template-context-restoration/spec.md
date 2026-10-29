## ADDED Requirements

### Requirement: 已就绪表单不重复等待新模板
系统 SHALL 在表单工作面已就绪并应用 manifest 后直接开始后续 `form.fill` 的字段处理，MUST NOT 因没有新的模板响应而额外等待完整模板超时。

#### Scenario: 新增行表单已应用后录入
- **WHEN** `editable_table.add_row` 已打开行编辑表单并应用其动态模板
- **AND** 后续 `form.fill` 开始时没有新的待处理模板
- **THEN** 系统 MUST 使用当前已绑定表单开始字段处理
- **AND** 系统 MUST NOT 再等待一次新模板响应

#### Scenario: 打开动作留下待应用模板
- **WHEN** 打开动作已捕获动态模板但尚未应用
- **AND** 后续 `form.fill` 开始时该模板对应工作面已就绪
- **THEN** 系统 MUST 在字段处理前应用该模板并重新绑定
- **AND** 系统 MUST NOT 为消除等待而跳过模板就绪和绑定校验

### Requirement: 确认框交接保持当前模板
系统 SHALL 在点击步骤以 `confirmation_required` 交接给后续确认动作时保持当前 manifest，不把确认框就绪解释为动态编辑工作面已关闭。

#### Scenario: 保存打开中间确认框
- **WHEN** 动态表单中的保存动作打开标准确认框
- **AND** 点击步骤以 `confirmation_required` 结束等待
- **THEN** 系统 MUST 保持当前表单 manifest
- **AND** 后续确认完成后 MUST 继续按实际工作面状态决定是否恢复父模板
