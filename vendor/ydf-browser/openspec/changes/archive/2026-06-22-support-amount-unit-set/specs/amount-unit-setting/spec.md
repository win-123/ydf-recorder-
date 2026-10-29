## ADDED Requirements

### Requirement: 金额单位 DSL
系统 SHALL 提供 `amount_unit.set` DSL，用统一语义设置 YonDiF 公共金额单位组件的单位。

#### Scenario: 合法金额单位值
- **WHEN** DSL 执行 `component: amount_unit`、`operation: set`
- **AND** `target.value` 为 `元` 或 `万元`
- **THEN** executor MUST 接受该步骤并调用 runtime 的金额单位设置能力
- **AND** 步骤报告 MUST 使用 action 名称 `amount_unit.set`

#### Scenario: 缺少或不支持的金额单位值
- **WHEN** DSL 执行 `amount_unit.set`
- **AND** `target.value` 缺失或不是 `元`、`万元`
- **THEN** DSL 校验 MUST 失败
- **AND** 错误信息 MUST 明确说明金额单位只支持 `元` 和 `万元`

#### Scenario: 不支持 label 覆盖入口
- **WHEN** DSL 执行 `amount_unit.set`
- **AND** target 包含 `label`
- **THEN** DSL 校验 MUST 失败
- **AND** 用例作者 MUST 使用固定公共组件入口，而不是为该语义指定按钮 label

### Requirement: 金额单位公共组件交互
系统 SHALL 在真实页面中完成金额单位公共组件的完整交互，而不要求 DSL 暴露按钮点击、radio 选择或弹窗确认细节。

#### Scenario: 设置单位为元
- **WHEN** runtime 执行 `amount_unit.set` 且目标值为 `元`
- **THEN** runtime MUST 点击当前页面的 `LCDSetAmtunit` 公共组件入口
- **AND** runtime MUST 在前景金额单位弹窗内选择 `元` radio
- **AND** runtime MUST 点击弹窗确认按钮完成交互

#### Scenario: 设置单位为万元
- **WHEN** runtime 执行 `amount_unit.set` 且目标值为 `万元`
- **THEN** runtime MUST 点击当前页面的 `LCDSetAmtunit` 公共组件入口
- **AND** runtime MUST 在前景金额单位弹窗内选择 `万元` radio
- **AND** runtime MUST 点击弹窗确认按钮完成交互

#### Scenario: 限定弹窗作用域
- **WHEN** 金额单位弹窗打开后，背景页面也存在 `元` 或 `万元` 文本
- **THEN** runtime MUST 只在可见前景弹窗内查找和点击 radio 选项
- **AND** runtime MUST NOT 通过全页面裸文本点击背景页面元素

### Requirement: 金额单位诊断
系统 SHALL 为金额单位公共组件步骤提供明确的成功报告和失败诊断。

#### Scenario: 成功设置后报告结果
- **WHEN** `amount_unit.set` 成功完成
- **THEN** 步骤 data MUST 记录目标单位 `value`
- **AND** 若 runtime 能读取最终选中项，步骤 data MUST 记录实际单位

#### Scenario: 缺少组件或弹窗时失败
- **WHEN** 当前页面没有可点击的 `LCDSetAmtunit` 公共组件入口，或点击后未出现可识别的金额单位弹窗
- **THEN** `amount_unit.set` MUST 失败
- **AND** 失败诊断 MUST 包含页面或弹窗文本，并在可用时包含截图路径
