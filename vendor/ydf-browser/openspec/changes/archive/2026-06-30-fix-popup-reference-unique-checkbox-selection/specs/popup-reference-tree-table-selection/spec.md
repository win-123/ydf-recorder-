## ADDED Requirements

### Requirement: 标量弹出参照值必须唯一确定单个候选
系统 SHALL 将 `form.fill` 的标量弹出参照值解释为单目标选择，并在标量隐式过滤后的当前有效候选范围内只接受唯一业务候选。

#### Scenario: 标量短值过滤出唯一候选
- **WHEN** `form.fill` 为弹出参照字段填写标量值 `二级采购项目`
- **AND** 运行时使用该值过滤后只有业务候选 `360000241010010000008 二级采购项目`
- **THEN** 运行时 MUST 选择该唯一候选并按当前参照确认规则完成字段回填
- **AND** 运行时 MUST NOT 要求 DSL 为唯一候选补充完整代码前缀

#### Scenario: 标量短值过滤出多个候选
- **WHEN** `form.fill` 的标量弹出参照值过滤出两个或更多不同业务候选
- **THEN** 运行时 MUST 失败并报告匹配候选数量
- **AND** 运行时 MUST NOT 默认选择第一条或勾选全部候选
- **AND** 错误信息 MUST 提示使用更完整的值、`first_available`、`row_number`、列表或 `selections` 明确选择意图

#### Scenario: 同一业务行的 DOM 副本不构成歧义
- **WHEN** 当前弹出参照因固定列、虚拟滚动或布局结构为同一业务候选渲染多个 DOM 行副本
- **THEN** 运行时 MUST 在唯一性判断前合并同一业务候选副本
- **AND** 运行时 MUST NOT 仅因 DOM 副本数量大于一而报告多候选歧义

#### Scenario: 显式位置选择不受唯一性约束
- **WHEN** 弹出参照目标显式使用 `first_available` 或 `row_number`
- **THEN** 运行时 SHALL 按既有位置选择语义选择候选
- **AND** 标量值的唯一性要求 MUST NOT 改变该显式行为

#### Scenario: 显式多选不受单目标约束
- **WHEN** 弹出参照字段使用列表、`values` 或 `selections` 表达多个目标
- **THEN** 运行时 SHALL 按既有多选语义处理每个显式目标
- **AND** 运行时 MUST NOT 将整个多选目标集合按标量唯一性规则拒绝
