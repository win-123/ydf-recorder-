# query-resetting Specification

## Purpose

定义 `query.reset` 在 YonDiF 查询区中的 DSL、前景作用域、重置按钮定位和报告要求，确保查询重置不会误点背景或页面其他同名动作。

## Requirements
### Requirement: 查询重置具有独立 DSL 操作
系统 SHALL 提供 `component: query`、`operation: reset`、`target: {}` 的组件操作，用于触发当前查询区的重置动作。

#### Scenario: 接受空目标
- **WHEN** 用例声明 `query.reset` 且 `target` 为空对象
- **THEN** DSL 校验 SHALL 接受该步骤并将其分派到查询重置执行路径

#### Scenario: 重置目标拒绝不受支持属性
- **WHEN** `query.reset target` 包含任意属性
- **THEN** DSL 校验 MUST 失败并报告该属性不受支持

### Requirement: 查询重置限定于唯一前景查询区
系统 MUST 将 `query.reset` 限定在当前单据模板中唯一的前景可见查询区，不得把页面其他区域或背景层的同名按钮作为候选。

#### Scenario: 使用唯一前景查询区
- **WHEN** 当前页面存在唯一的前景可见 `LCDQueryString` 查询区
- **THEN** runtime MUST 只在该查询区根内定位并点击重置按钮
- **AND** runtime MUST 覆盖主页面和子 frame 中属于该查询区的候选

#### Scenario: 多个前景查询区构成歧义
- **WHEN** 同一前景存在多个可见查询区且无参数 DSL 无法唯一确定目标
- **THEN** runtime MUST 让步骤失败并报告查询区歧义
- **AND** runtime MUST NOT 按 DOM 顺序任选一个查询区

#### Scenario: 页面没有查询区
- **WHEN** 当前单据模板不存在可操作的查询区
- **THEN** executor MUST 让 `query.reset` 失败并说明当前页面不包含查询区

### Requirement: 查询重置使用严格的可见按钮定位
系统 SHALL 优先使用查询区内明确的 `reset_btn` 身份定位重置按钮，并可在同一查询区内使用可点击元素的精确“重置”文本作为后备；系统 MUST NOT 使用全页面同名文本兜底。

#### Scenario: 存在明确重置身份
- **WHEN** 唯一目标查询区内存在可见且可点击的 `reset_btn`
- **THEN** runtime SHALL 点击该按钮并等待页面稳定

#### Scenario: 查询区内存在精确重置文本
- **WHEN** 目标查询区没有可用的 `reset_btn`，但区内存在唯一可见且可点击的精确“重置”文本
- **THEN** runtime SHALL 点击该候选并等待页面稳定

#### Scenario: 查询区外存在同名重置文本
- **WHEN** 查询区外的工具栏、弹窗或其他区域存在同名“重置”按钮
- **THEN** runtime MUST NOT 将这些按钮作为 `query.reset` 候选

#### Scenario: 重置隐藏在更多动作中
- **WHEN** 查询区内没有直接可见的重置按钮，但“更多”菜单可能包含重置动作
- **THEN** runtime MUST 让步骤失败并报告未找到可点击查询重置动作
- **AND** runtime MUST NOT 自动展开“更多”菜单

### Requirement: 查询重置报告动作诊断但不断言字段值
系统 SHALL 在正确点击重置按钮并等待页面稳定后报告 `query.reset` 成功，并记录目标查询区身份、按钮名称和实际定位来源；系统 MUST NOT 将字段全部为空或表格勾选被清除作为通用成功条件。

#### Scenario: 重置动作完成
- **WHEN** runtime 在唯一目标查询区内点击重置按钮并完成页面稳定等待
- **THEN** 步骤结果 SHALL 使用动作名 `query.reset` 和消息“查询条件已重置”
- **AND** 结果数据 SHALL 包含查询区 fieldid、按钮“重置”和定位来源

#### Scenario: 页面恢复默认查询值
- **WHEN** 页面点击重置后恢复自身定义的默认查询条件而不是将所有字段清空
- **THEN** `query.reset` SHALL 仍按动作完成语义报告成功

#### Scenario: 页面同时清除表格勾选
- **WHEN** 页面点击重置后同时清除表格行勾选状态
- **THEN** `query.reset` SHALL 不把该副作用纳入成功或失败判断

### Requirement: 查询搜索不能表达查询重置
系统 MUST 拒绝使用 `query.search target.button: 重置` 表达查询重置，并引导 DSL 作者使用独立的 `query.reset` 操作。

#### Scenario: 查询搜索指定重置按钮
- **WHEN** 用例将 `query.search target.button` 设置为“重置”
- **THEN** DSL 校验 MUST 失败并提示使用 `query.reset`

#### Scenario: 查询搜索使用提交按钮变体
- **WHEN** `query.search target.button` 指定正常的查询或搜索按钮变体
- **THEN** 系统 SHALL 保持现有查询提交行为

### Requirement: 查询重置由聚焦真实 DSL 用例证明
系统 MUST 用真实单据页 DSL 证明查询重置能力，且该用例 SHALL 先设置一个已知查询条件再执行 `query.reset`。

#### Scenario: 单位资金收入确认重置已知筛选条件
- **WHEN** 真实用例打开“单位资金收入确认”的“未确认”页签，设置一个已知查询条件后执行 `query.reset`
- **THEN** `query.reset` 步骤 SHALL 成功并报告目标查询区与定位来源
- **AND** 运行时 DOM 或截图证据 SHALL 证明该条件恢复为页面定义的初始状态
- **AND** 用例 MUST NOT 以表格行勾选是否清除作为查询重置证据
