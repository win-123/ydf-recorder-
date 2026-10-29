## ADDED Requirements

### Requirement: 连续参照确认按原选择面的前景状态判定完成
独立 `popup_reference.select` 默认确认后，系统 SHALL 判定本次选择的参照是否已退出前景交互；若新的独立参照已接管交互，旧参照保留在后台 MUST NOT 导致本次选择失败。系统 MUST 保留原参照仍可交互、通知拒绝和证据不足时的失败行为。

#### Scenario: 确认项目后立即打开指标参照
- **WHEN** 本次参照已选中目标并点击确定
- **AND** 新的独立参照成为前景可交互工作面，原参照已隐藏或被其覆盖
- **THEN** 本次选择 MUST 返回 `confirmed=true`
- **AND** 系统 MUST NOT 点击下一参照的确定或重试原参照确认
- **AND** 后续选择 MUST 可按下一参照标题继续执行

#### Scenario: 原参照确认后仍然活跃
- **WHEN** 确认后原参照仍作为前景候选选择面可交互
- **THEN** 系统 MUST 继续等待或失败
- **AND** 系统 MUST NOT 因页面存在另一个背景参照就报告完成

#### Scenario: 字段参照仍要求真实回填
- **WHEN** 表单、查询或可编辑表格字段参照确认后切换选择面
- **THEN** 原入口的字段回填校验 MUST 保留
- **AND** 前景切换 MUST NOT 替代字段值确认
