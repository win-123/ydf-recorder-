## ADDED Requirements

### Requirement: 可见字段约束具有可追溯观察证据

AI 观察模式的 DOM 摘要 MUST 保留可见控件的关联字段标签、必填状态及来源、公开原生约束属性和输入提示。该信息 MUST 仅描述当前界面证据，不改变测试 DSL、动作结果或保存校验。

#### Scenario: 平台标签标记必填
- **WHEN** 可见控件的同一表单项可见标签具有平台必填标记
- **THEN** 摘要 MUST 将该控件标为必填，并记录标签来源与字段标签
- **AND** MUST NOT 将其他表单项或其他 frame 的同名标签用于该控件

#### Scenario: 原生必填与未知状态
- **WHEN** 控件具有原生 required 或显式 aria-required 声明
- **THEN** 摘要 MUST 保留必填状态及证据来源，正向必填证据优先
- **AND** 缺少显式必填证据时 MUST 输出未知，MUST NOT 以未标记推断可选

#### Scenario: 格式与长度约束仅保留公开事实
- **WHEN** 可见控件声明 type、pattern、minlength、maxlength、min、max、step 或 placeholder
- **THEN** 摘要 MUST 保留对应公开属性及提示
- **AND** MUST NOT 将提示、字段名称或静态模板解释为完整业务正则或动态必填规则

#### Scenario: 安全和运行边界
- **WHEN** 采集包含敏感控件、隐藏控件或超出预算的信息
- **THEN** 系统 MUST 沿用脱敏、可见性和大小限制，并明确标记约束文本截断；新增提示及约束属性不得泄漏敏感控件内容
- **AND** 未启用 AI 观察时 MUST NOT 增加采集或改变普通测试结果

#### Scenario: 编写者使用约束证据
- **WHEN** 技能指导编写新增录入用例
- **THEN** 技能 MUST 要求先核对当前字段约束和未知项，再生成最小录入数据
- **AND** MUST 说明保存提示仍可能暴露未公开的业务校验，不将提示或公开属性视为穷尽约束
