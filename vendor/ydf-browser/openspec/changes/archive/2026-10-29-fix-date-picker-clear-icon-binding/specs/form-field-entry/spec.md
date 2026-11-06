## MODIFIED Requirements

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

#### Scenario: 已有日期值时不把清空图标作为输入
- **WHEN** `YDFDatePicker` 已有默认日期并显示清空图标
- **AND** 日期容器、内部输入和清空图标共享同一逻辑字段身份
- **THEN** 系统 MUST 使用真实日期控件及其内部输入录入目标值
- **AND** 系统 MUST NOT 将清空图标或其它装饰作为日期录入目标

#### Scenario: 日期确认不接受自行写入的装饰属性
- **WHEN** 日期录入后真实输入框仍保留原值
- **AND** 非输入节点的 `title` 或 `value` 恰好等于目标值
- **THEN** `form.fill` MUST 失败，MUST NOT 将装饰属性作为字段真实回填证据

#### Scenario: 同根多个日期控件保持不兼容
- **WHEN** 同一逻辑字段身份内存在多个可操作日期控件，无法唯一确定目标
- **THEN** 系统 MUST 拒绝按 DOM 顺序任选一个日期控件
- **AND** 字段录入 MUST 失败并保留不兼容诊断
