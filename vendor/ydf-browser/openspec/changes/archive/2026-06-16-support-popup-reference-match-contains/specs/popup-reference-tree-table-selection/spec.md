## ADDED Requirements

### Requirement: 弹出参照表格匹配支持 contains
系统 SHALL 在 `form.fill` 结构化弹出参照目标和独立 `popup_reference.select` 目标中支持 `match.contains`，并将其作为表格候选行的包含匹配目标。

#### Scenario: 独立弹出参照按 contains 选择表格候选
- **WHEN** 用例在已打开的弹出参照中执行 `popup_reference.select`，且 `target.match.column` 为 `用户名称`、`target.match.contains` 为 `财会`
- **AND** 当前弹窗表格中存在 `用户名称` 单元格文本包含 `财会` 的候选行，例如 `财会监督1`
- **THEN** 运行时 MUST 在当前弹窗根内选择该候选行
- **AND** 运行时 MUST 按当前弹出参照确认规则点击确认按钮或等待弹窗关闭

#### Scenario: 表单结构化参照按 contains 选择表格候选
- **WHEN** `form.fill` 的弹出参照字段值包含 `match.column` 和 `match.contains`
- **AND** 参照弹窗过滤后存在目标列文本包含该值的候选行
- **THEN** 运行时 MUST 复用弹出参照表格匹配规则选择该候选行
- **AND** 步骤结果 MUST 记录被选中的 `match` 结构，且不得把目标对象字符串化为普通文本录入

#### Scenario: contains 失败诊断保留目标值
- **WHEN** 弹出参照目标使用 `match.contains` 但当前弹窗表格没有任何候选行匹配
- **THEN** 运行时 MUST 失败并保留弹窗诊断
- **AND** 诊断中的表格匹配调试信息 MUST 将 `wantedValue` 设置为 `match.contains` 的值，而不是空字符串
