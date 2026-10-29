## ADDED Requirements

### Requirement: 普通树选择先搜索再展开
系统 SHALL 在普通页面树控件存在可用搜索框时，让显式 `tree.select` 目标优先通过树内搜索缩小候选范围，再选择目标节点。

#### Scenario: 展开节点前先搜索可见树
- **WHEN** 用例执行 `tree.select`，目标为 `label: 流程管理`
- **AND** 当前模板解析出的目标树区域内存在可见搜索输入框
- **THEN** runtime MUST 在该树区域内输入 `流程管理` 并触发树搜索
- **AND** runtime MUST 在搜索后的当前 DOM 中选择精确匹配的树节点
- **AND** runtime MUST NOT 在搜索前逐个展开所有折叠节点

#### Scenario: 搜索限定在已解析树区域
- **WHEN** 用例执行带 `target.name` 的 `tree.select`
- **AND** 当前页面存在多个树或多个搜索输入框
- **THEN** runtime MUST 只在 executor 解析出的目标树区域内查找和使用搜索框
- **AND** runtime MUST NOT 使用页面查询区、顶部导航或其他树组件中的搜索框

### Requirement: 树搜索保持既有选择语义
系统 SHALL 在通过搜索定位普通页面树节点后，保持现有树节点选择语义和幂等行为。

#### Scenario: 搜索后优先点击勾选控件
- **WHEN** 搜索后的目标树节点包含 checkbox 或 radio 选择控件
- **THEN** runtime MUST 优先点击节点前的选择控件
- **AND** runtime MUST 在控件已选中时保持已选状态，不得重复点击导致反选

#### Scenario: 多节点选择逐个搜索
- **WHEN** 用例通过 `target.labels` 或 `target.values` 选择多个普通树节点
- **THEN** runtime MUST 对每个目标分别尝试树内搜索和选择
- **AND** 每个目标的选择结果 MUST 保持与单个 `target.label` 相同的幂等规则

### Requirement: 树搜索失败回退既有遍历
系统 SHALL 在树搜索不可用或不能定位目标节点时，回退到既有展开遍历逻辑。

#### Scenario: 没有搜索框时回退展开
- **WHEN** 用例执行 `tree.select`
- **AND** 目标树区域内没有可见可用的搜索输入框
- **THEN** runtime MUST 使用既有折叠节点展开和节点查找流程
- **AND** 用例不需要修改 DSL

#### Scenario: 搜索未命中后继续展开
- **WHEN** 树搜索已执行但目标节点仍不可见
- **THEN** runtime MUST 继续使用既有展开遍历查找目标节点
- **AND** 如果最终仍找不到目标，错误信息 MUST 保留目标标签和树区域上下文

### Requirement: 树搜索诊断可追踪
系统 SHALL 在普通页面树选择结果或错误诊断中保留树搜索尝试信息。

#### Scenario: 搜索成功记录元信息
- **WHEN** `tree.select` 通过树内搜索成功选择目标节点
- **THEN** step result MUST 包含已解析的 `tree_fieldid`
- **AND** step result MUST 记录本次使用了树搜索

#### Scenario: 搜索失败记录回退原因
- **WHEN** 树搜索尝试失败并回退到展开遍历
- **THEN** runtime diagnostics MUST 记录搜索框缺失、填值失败、搜索结果为空或已回退遍历中的至少一种原因
