## ADDED Requirements

### Requirement: 可编辑表格新增行按目标表格身份定位
系统 SHALL 在执行 `editable_table.add_row` 时将 `target.table` 解析为当前前景可编辑表格身份，并用该身份限定运行时新增入口；当页面分组标题、模板表格 label 和运行时可见表头文本不一致时，系统仍 MUST 在能唯一解析目标表格的情况下点击正确的新增入口。

#### Scenario: 分组标题匹配到模板表格新增入口
- **WHEN** DSL 文档执行 `editable_table.add_row`，`target.table` 为页面分组标题 `缴款明细信息`
- **AND** 当前模板中唯一对应的可编辑表格 label 为 `缴库明细表格`
- **AND** 运行时 DOM 中目标表格附近只稳定显示列头 `缴款金额`、`政府非税收入项目`、`收入分类` 和 `备注`
- **THEN** 系统 MUST 将 `缴款明细信息` 解析到该目标可编辑表格
- **AND** 系统 MUST 在该目标表格作用域内点击 `新增`
- **AND** 系统 MUST NOT 因运行时 DOM 缺少 `缴款明细信息` 或 `缴库明细表格` 可见文本而拒绝点击

#### Scenario: 模板表格名不依赖运行时可见标题
- **WHEN** DSL 文档执行 `editable_table.add_row`，`target.table` 为模板表格 label `缴库明细表格`
- **AND** 运行时目标表格附近没有可见的 `缴库明细表格` 标题
- **THEN** 系统 MUST 使用模板表格身份、表格 fieldid、列身份或等价目标 root 约束新增入口
- **AND** 系统 MUST NOT 只因附近标题匹配分数不足而报告 `可编辑表格名称未匹配`

#### Scenario: 后续行录入复用同一表格身份
- **WHEN** DSL 文档先执行 `editable_table.add_row`，再执行 `editable_table.fill_row`
- **AND** 两个步骤的 `target.table` 都为页面分组标题 `缴款明细信息`
- **AND** 当前模板中唯一对应的可编辑表格 label 为 `缴库明细表格`
- **THEN** 系统 MUST 在两个步骤中都将 `缴款明细信息` 解析到同一个目标可编辑表格
- **AND** `editable_table.fill_row` MUST 使用解析后的表格身份定位列和行

#### Scenario: 多个候选表格无法唯一解析时失败
- **WHEN** DSL 文档执行 `editable_table.add_row` 且提供了 `target.table`
- **AND** executor 或 runtime 找到多个可编辑表格候选，无法唯一判断哪个候选属于该目标
- **THEN** 当前 `editable_table.add_row` 步骤 MUST 失败
- **AND** 错误信息 MUST 包含 `target.table`、候选表格 label、候选 fieldid 或可见表头摘要

### Requirement: 可编辑表格新增行成功必须验证真实数据行
系统 MUST 在 `editable_table.add_row` 点击新增入口后验证目标可编辑表格出现真实可编辑数据行；如果目标表格仍为空态、仍显示 `暂无数据`，或没有可用于后续 `editable_table.fill_row` 的数据行，当前新增行步骤 MUST 失败并输出诊断。

#### Scenario: 点击新增后出现可编辑行才成功
- **WHEN** DSL 文档执行 `editable_table.add_row`
- **AND** 运行时点击了目标表格作用域内的 `新增`
- **AND** 目标表格从空态变为包含真实数据行，例如第一行显示序号 `1`
- **THEN** 当前步骤 MUST 报告成功
- **AND** 步骤结果 SHALL 包含目标表格身份、点击入口诊断和新增后的行状态摘要

#### Scenario: 点击后仍是暂无数据时当前步骤失败
- **WHEN** DSL 文档执行 `editable_table.add_row`
- **AND** 运行时点击了某个 `新增` 入口
- **AND** 等待后目标表格仍只包含 `暂无数据` 或没有可编辑数据行
- **THEN** 当前步骤 MUST 失败
- **AND** 错误信息 MUST 指向新增行未生效
- **AND** 系统 MUST NOT 将该步骤报告为成功并把失败延迟到后续 `editable_table.fill_row`

#### Scenario: 未指定表格名保持单表兼容
- **WHEN** DSL 文档执行 `editable_table.add_row` 且未提供 `target.table`
- **AND** 当前前景页面只有一个可识别的可编辑表格新增入口
- **THEN** 系统 SHALL 保持既有点击语义
- **AND** 系统 MUST 仍执行新增后真实数据行校验
