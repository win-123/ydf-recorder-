## ADDED Requirements

### Requirement: 表单填充参照关闭后恢复父表单模板
当 `form.fill` 内的弹出参照已完成选择并关闭，且本次表单填充实际应用了参照动态模板时，executor SHALL 使用现有运行时可见性与身份评分恢复父表单模板；没有本次动态模板应用证据时 MUST NOT 仅以 `form.fill` 上下文授权恢复。

#### Scenario: 已应用的表单参照模板关闭后恢复
- **WHEN** `form.fill` 完成弹出参照选择并确认参照弹窗已关闭
- **AND** 本次 `form.fill` 在选择后实际应用了参照动态模板
- **AND** 父表单模板的运行时恢复证据强于当前参照模板
- **THEN** executor MUST 恢复父表单模板
- **AND** 后续组件动作 MUST 使用父表单 manifest 重新绑定

#### Scenario: 没有应用 post-fill 动态模板时保持当前模板
- **WHEN** `form.fill` 完成弹出参照选择
- **AND** 本次 `form.fill` 没有在选择后应用动态模板
- **AND** 当前模板上下文为 `form.fill`
- **THEN** executor MUST 保持当前模板和模板栈
- **AND** executor MUST NOT 因 `form.fill` 上下文而弹出更早的父模板

#### Scenario: 参照模板仍是前景工作面时保持当前模板
- **WHEN** `form.fill` 完成弹出参照选择并应用参照动态模板
- **AND** 当前参照模板仍暴露前景可操作身份，或父表单恢复证据不足
- **THEN** executor MUST 保持当前参照模板

#### Scenario: 父子模板共享稳定动作身份
- **WHEN** `form.fill` 已应用的关闭参照模板与父表单模板包含相同 fieldid 的保存、提交、取消或确认动作
- **AND** 运行时仅匹配到该共享动作身份
- **THEN** executor MUST NOT 仅凭共享动作身份判定参照模板仍是前景工作面
- **AND** executor MUST 继续使用其他非共享身份与可见性评分决定是否恢复
