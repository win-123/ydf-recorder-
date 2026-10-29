## ADDED Requirements

### Requirement: 可编辑表格新增行验证限定目标表格
系统 MUST 在执行 `editable_table.add_row` 时，将点击后的新增行验证限定到 DSL 解析出的目标可编辑表格身份、目标 `fieldid` 或等价目标 root；目标表格外的相邻表格、外层表单容器、背景列表和其他明细表行不得作为当前新增成功证据。

#### Scenario: 相邻表格已有行不能证明目标新增成功
- **WHEN** DSL 文档执行 `editable_table.add_row`，目标表格为 `需求清单`
- **AND** executor 已将目标表格解析为 `table_fieldid=cgbd_table`
- **AND** 页面同一表单区域内存在其他可编辑表格或明细表，且这些表格已有 `公司业绩`、`交付时间`、`产品质保` 等数据行
- **AND** 点击 `需求清单` 区域的 `新增` 后，`需求清单` 仍只显示空态、表头或 `+ 新增`
- **THEN** 当前 `editable_table.add_row` 步骤 MUST 失败
- **AND** 系统 MUST NOT 将相邻表格的已有数据行计入 `需求清单` 的新增后 `row_state`
- **AND** 系统 MUST NOT 把失败延迟到后续 `editable_table.fill_row`

#### Scenario: 目标表格出现真实可编辑行才报告成功
- **WHEN** DSL 文档执行 `editable_table.add_row`
- **AND** 运行时已根据 `target.table`、目标表格 `fieldid` 或目标列身份定位到目标表格 root
- **AND** 点击新增入口后，目标表格 root 内出现可供后续 `editable_table.fill_row` 定位的真实数据行
- **THEN** 当前步骤 MUST 报告成功
- **AND** 步骤结果 SHALL 包含目标表格身份、点击入口诊断和限定在目标表格 root 内的新增后 `row_state`

#### Scenario: 无法唯一确认目标验证 root 时失败
- **WHEN** DSL 文档执行 `editable_table.add_row` 且提供了 `target.table`
- **AND** 运行时点击了候选新增入口，但无法将点击后的验证 root 唯一限定到目标表格身份、目标 `fieldid` 或目标列身份
- **THEN** 当前步骤 MUST 失败
- **AND** 错误信息 MUST 包含 `target.table`、目标 `table_fieldid` 或目标列身份摘要，以及候选 root 的可见文本或行状态摘要
