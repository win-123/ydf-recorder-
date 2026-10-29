## ADDED Requirements

### Requirement: 可编辑表格商品参照 first_available 选择当前可见业务行
系统 MUST 在 `editable_table.fill_row` 录入可编辑表格参照列时，将结构化目标 `first_available: true` 应用于当前字段打开的有效候选参照层，并选择当前可见候选表格中的第一条业务数据行。

#### Scenario: 发票内容明细商品参照选择首条商品
- **WHEN** DSL 执行 `editable_table.fill_row`
- **AND** 目标表格为 `发票内容明细`
- **AND** 字段 `商品` 的组件为 `YDFTableModalSelect`
- **AND** 字段值为 `first_available: true`
- **AND** 当前商品参照弹窗显示一条可见业务行 `0702154531736 / 商品_0702154531736`
- **THEN** runtime MUST 在当前商品参照弹窗内选择该业务行
- **AND** runtime MUST 等待 `商品` 单元格回填或确认参照选择完成
- **AND** 当前 `editable_table.fill_row` MUST NOT 因空状态候选、背景页面文本或非当前字段候选层而失败

#### Scenario: 当前字段候选层优先于背景和旧弹层
- **WHEN** 前景业务弹窗、背景页面或旧弹层中存在其它表格、空状态或说明文本
- **AND** 当前 `editable_table.fill_row` 字段已打开新的商品候选参照层
- **THEN** runtime MUST 在当前字段候选参照层内执行 `first_available`
- **AND** runtime MUST NOT 将背景页面、外层业务表单、业务助手 iframe 或已关闭旧弹层作为商品候选根

### Requirement: 可编辑表格 first_available 失败诊断区分空状态和业务行
系统 SHALL 在可编辑表格参照列 `first_available` 失败时输出能区分业务无数据、空状态被排除、业务行未选中和候选根识别错误的字段级诊断。

#### Scenario: 业务行可见但候选未选中
- **WHEN** 商品参照弹窗诊断文本能读取到业务行 `0702154531736 / 商品_0702154531736`
- **AND** runtime 未能选中该行
- **THEN** 当前字段失败信息 MUST 包含表格名、行号、列名、组件类型和结构化目标
- **AND** 诊断 SHALL 包含有效候选数量、实际尝试候选、候选来源、候选文本摘要和截图路径
- **AND** 诊断 MUST NOT 只报告空状态候选而不暴露可见业务行摘要

#### Scenario: 真实无业务候选
- **WHEN** 当前商品候选参照层只包含空状态或查询后无结果
- **THEN** 当前字段失败信息 MUST 明确说明没有有效业务候选
- **AND** runtime MUST 保留空状态文本或截图，避免误导为 DSL 写法错误
