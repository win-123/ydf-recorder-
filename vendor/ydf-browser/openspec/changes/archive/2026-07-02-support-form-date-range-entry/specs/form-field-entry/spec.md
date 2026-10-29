## ADDED Requirements

### Requirement: 日期范围字段录入
系统 SHALL 在 `form.fill` 中支持 `YDFDateRange` 日期范围字段，并将标量区间值解释为开始日期和结束日期的业务范围录入。

#### Scenario: 标量日期范围写法录入
- **WHEN** DSL 执行 `form.fill` 填写 `YDFDateRange` 字段，值为 `2026-01-01~2026-01-12`
- **THEN** runtime MUST 将该值解析为开始日期 `2026-01-01` 和结束日期 `2026-01-12`
- **AND** runtime MUST 真实录入日期范围控件的内部状态
- **AND** runtime MUST NOT 仅向外层字段根节点写入 `value` 或 `title` 后判定成功

#### Scenario: 日期范围分隔符允许空格
- **WHEN** DSL 执行 `form.fill` 填写 `YDFDateRange` 字段，值为 `2026-01-01 ~ 2026-01-12`
- **THEN** runtime MUST 接受该写法
- **AND** runtime MUST 在报告中将实际区间值归一化为 `2026-01-01~2026-01-12`

#### Scenario: 日期范围真实确认
- **WHEN** runtime 完成 `YDFDateRange` 字段录入
- **THEN** runtime MUST 从真实可见值、真实 input value、组件内部可读值或业务保存结果确认该字段已回填
- **AND** 如果只能读回外层字段根节点上由 runtime 自行写入的属性，`form.fill` MUST 失败
- **AND** 失败诊断 MUST 包含字段名、目标区间值、实际读数和运行时 selector 或字段身份

#### Scenario: 对账起止日期保存不再报必填
- **WHEN** 用例填写 `对账起止日期: "2026-01-01~2026-01-12"` 并执行保存
- **THEN** runtime MUST 证明保存流程不再因为 `对账起止日期` 为空而失败
- **AND** 报告 MUST 保留该字段的归一化实际值和确认信息
