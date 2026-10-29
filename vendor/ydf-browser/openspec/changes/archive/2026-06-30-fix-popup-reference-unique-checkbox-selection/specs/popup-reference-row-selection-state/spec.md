## ADDED Requirements

### Requirement: 匹配候选存在选择控件时必须验证真实选中态
系统 MUST 在标量值或 `match` 选择命中的弹出参照候选包含可见 checkbox/radio 时，确认该选择控件真实进入选中态后才报告选择成功。

#### Scenario: 标量短值命中带 checkbox 的唯一候选
- **WHEN** `form.fill` 的标量值 `二级采购项目` 唯一命中候选 `360000241010010000008 二级采购项目`
- **AND** 候选行前存在可见且未禁用的 checkbox
- **THEN** 运行时 MUST 点击 checkbox 或其可交互包装节点
- **AND** 运行时 MUST 在确认弹窗前验证 checkbox 呈现 `checked=true`、`aria-checked=true` 或明确 checked 状态

#### Scenario: 行高亮不能替代 checkbox 选中
- **WHEN** 标量值或 `match` 命中的候选行获得焦点、蓝色高亮、`active` 或宽泛行级 `selected` 状态
- **AND** 候选内可见 checkbox/radio 仍未选中
- **THEN** 运行时 MUST NOT 将该候选判定为业务选择成功
- **AND** 运行时 MUST 继续尝试点击真实选择控件，仍无法选中时失败并保留诊断

#### Scenario: 结构化 match 复用相同选择态要求
- **WHEN** `form.fill` 或 `popup_reference.select` 使用 `match.equals` 或 `match.contains` 命中带 checkbox/radio 的候选
- **THEN** 运行时 MUST 复用与标量值相同的选择控件点击和选中态验证规则
- **AND** 运行时 MUST NOT 在只完成文本匹配或行点击后直接返回成功

#### Scenario: 无选择控件候选保持兼容
- **WHEN** 标量值或 `match` 命中的候选没有可见 checkbox/radio
- **THEN** 运行时 SHALL 继续使用既有候选点击、字段回填或弹窗关闭判定
- **AND** 运行时 MUST NOT 要求该候选产生不存在的 checked 状态
