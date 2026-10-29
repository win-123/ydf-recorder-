## ADDED Requirements

### Requirement: 视口外表单控件 pointer 状态保持未知
系统在扫描具有平台精确身份的可见、可编辑表单控件时，若控件仅因当前滚动位置完全位于浏览器视口外而无法执行 `elementFromPoint` 命中，pointer 可达性 MUST 记录为未知，不得记录为确定不可达。未知状态 SHALL 只允许唯一精确身份或同一逻辑根内唯一真实输入以未验证契约绑定，实际录入仍必须由浏览器滚动到目标后执行。

#### Scenario: 视口外唯一 textarea 保持可录入
- **WHEN** 动态新增表单中的 `YDFTextArea` 具有唯一平台精确身份并且当前完全位于视口外
- **AND** 该控件可见、可编辑、未禁用且未只读
- **THEN** DOM 扫描 MUST 将其 pointer 可达性记录为未知
- **AND** `form.fill` SHALL 以未验证契约绑定该唯一真实 textarea，并由浏览器滚动后录入

#### Scenario: 视口内被遮挡控件继续失败关闭
- **WHEN** 同一平台精确身份存在视口内候选，但目标点被其它前景元素遮挡或控件明确设置 `pointer-events: none`
- **THEN** DOM 扫描 MUST 将该候选记录为确定不可接收 pointer
- **AND** 系统 MUST NOT 因视口外未知状态规则将该候选绑定为录入目标

#### Scenario: 视口外同根多输入保持不兼容
- **WHEN** 同一平台精确身份逻辑根内存在两个或更多可见、可编辑的真实输入
- **AND** 这些输入当前均位于视口外
- **THEN** 系统 MUST 保持平台精确身份状态不兼容
- **AND** 系统 MUST NOT 仅因 pointer 状态未知而选择 DOM 顺序中的第一个输入
