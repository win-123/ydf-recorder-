# tree-search-selection Specification

## Purpose
定义普通页面树控件在存在搜索框时的搜索优先选择行为，避免 `tree.select` 为查找目标节点逐层展开整棵树。
## Requirements
### Requirement: 普通树选择先搜索再展开
系统 SHALL 在普通页面树控件存在可用搜索框时，让显式 `tree.select` 目标优先通过树内搜索缩小候选范围，再选择目标节点；搜索框定位和节点交互 MUST 使用彼此独立且受目标树组件约束的作用域。

#### Scenario: 展开节点前先搜索可见树
- **WHEN** 用例执行 `tree.select`，目标为 `label: 流程管理`
- **AND** 当前模板解析出的目标树区域内存在可见搜索输入框
- **THEN** runtime MUST 在该树区域内输入 `流程管理` 并触发树搜索
- **AND** runtime MUST 在搜索后的当前 DOM 中选择精确匹配的树节点
- **AND** runtime MUST NOT 在搜索前逐个展开所有折叠节点

#### Scenario: 搜索限定在已解析树区域
- **WHEN** 用例执行带 `target.name` 的 `tree.select`
- **AND** 当前页面存在多个树或多个搜索输入框
- **THEN** runtime MUST 只在 executor 解析出的目标树组件区域内查找和使用搜索框
- **AND** runtime MUST NOT 使用页面查询区、顶部导航或其他树组件中的搜索框

#### Scenario: 节点交互限定在严格树根
- **WHEN** runtime 已为 `tree.select` 解析出目标树和可选搜索作用域
- **THEN** runtime MUST 只在严格目标树根内检查、匹配、展开和选择节点
- **AND** 搜索作用域中的树外文本 MUST NOT 被视为树节点命中

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
系统 SHALL 在树搜索不可用或不能定位目标节点时，回退到目标树内的既有展开遍历逻辑，且 MUST NOT 通过扩大节点匹配范围寻找树外同名文本。

#### Scenario: 没有搜索框时回退展开
- **WHEN** 用例执行 `tree.select`
- **AND** 目标树组件区域内没有可见可用的搜索输入框
- **THEN** runtime MUST 使用既有折叠节点展开和节点查找流程
- **AND** 用例不需要修改 DSL

#### Scenario: 树外存在同名文本时仍展开目标树
- **WHEN** 目标节点位于目标树的折叠父节点下
- **AND** 页面查询区、表格或其他树外区域存在与目标节点相同的可见文本
- **THEN** runtime MUST NOT 点击树外同名文本或提前报告成功
- **AND** runtime MUST 展开目标树并选择其中的目标节点

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

### Requirement: 树控件使用规则推导身份
系统 SHALL 在普通页面树选择和搜索中使用 `LCDTree` 容器 `divCode` 推导树内搜索框、搜索按钮、节点标题、展开图标和选择控件的运行时 `fieldid` 候选。

#### Scenario: 树搜索框按 tree divCode 定位
- **WHEN** 模板中目标树 `divCode=deptTree`
- **THEN** runtime MUST 优先在目标树作用域内尝试 `deptTree_search_input` 作为搜索输入候选
- **AND** runtime MUST 优先尝试 `deptTree_search_suffix` 作为搜索触发候选

#### Scenario: 树节点 key 规则不扩大搜索范围
- **WHEN** runtime 已知目标节点 key 并能推导 `deptTree_tree_title_<key>` 或 `deptTree_tree_checkbox_<key>`
- **THEN** runtime MUST 只在已解析目标树根内使用这些候选
- **AND** runtime MUST NOT 因规则候选失败而点击树外同名文本
