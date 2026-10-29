## ADDED Requirements

### Requirement: 可编辑表格空态 placeholder 新增按目标表格 root 判定
系统 MUST 在执行 `editable_table.add_row` 点击空态 placeholder 新增入口时，将点击前后行状态验证限定到 DSL 解析出的目标表格 root；placeholder 按钮自身、外层表单容器、相邻表格和背景表格不得作为目标表格行状态证据。系统 SHALL 仅在点击前目标表格 root 已可靠确认存在真实数据行时启用一次受控重试；空目标表格首次点击后出现真实可编辑行时 MUST 直接报告成功。

#### Scenario: 空目标表格 placeholder 首次新增成功
- **WHEN** DSL 文档执行 `editable_table.add_row`，目标表格解析为 `table_fieldid=table2`
- **AND** 点击前 `table2` 对应目标表格为空态，只显示 placeholder 新增入口
- **AND** 运行时点击 `.ydf-table-placeholder-add-button` 或等价 placeholder 新增入口
- **AND** 点击后 `table2` 对应目标表格 root 内出现第一条真实可编辑数据行
- **THEN** 当前 `editable_table.add_row` 步骤 MUST 报告成功
- **AND** 系统 MUST NOT 对同一 placeholder 新增入口执行第二次点击
- **AND** 步骤结果 SHALL 包含目标表格身份、候选入口和点击后的目标 root 行状态摘要

#### Scenario: placeholder 按钮不能作为验证 root
- **WHEN** `editable_table.add_row` 选中的候选入口是 `.ydf-table-placeholder-add-button`、`.ydf-table-placeholder-add` 或等价空态新增按钮
- **AND** DSL 目标已经解析出 `target.table`、目标 `table_fieldid` 或目标列身份
- **THEN** 系统 MUST 在点击前后按目标表格身份解析验证 root
- **AND** 系统 MUST NOT 将 placeholder 按钮自身的文本、外层表单容器行数、相邻表格行数或背景表格行数计入目标表格 `row_state`
- **AND** 如果无法唯一确认目标验证 root，当前步骤 MUST 失败并输出目标表格身份、候选入口和候选 root 诊断

#### Scenario: 空态新增后仍无真实行时失败
- **WHEN** DSL 文档执行 `editable_table.add_row`
- **AND** 点击前目标表格 root 为空态
- **AND** 运行时点击目标表格 placeholder 新增入口后，目标表格 root 仍没有真实可编辑数据行
- **THEN** 当前 `editable_table.add_row` 步骤 MUST 失败
- **AND** 错误信息 MUST 指向新增行未生效，并包含目标表格身份、placeholder 候选入口和点击后的目标 root 行状态
- **AND** 系统 MUST NOT 因外层或相邻表格已有行而报告成功

#### Scenario: 非空目标表格未增长时仍可受控重试
- **WHEN** DSL 文档执行 `editable_table.add_row`
- **AND** 点击前系统已可靠确认目标表格 root 内已有 1 条真实数据行
- **AND** 首次点击目标表格新增入口后没有打开行编辑表单模板，且目标表格 root 内仍只有 1 条真实数据行
- **THEN** 系统 SHALL 重新收口交互状态并重新解析同一目标表格作用域内的新增候选
- **AND** 系统 MUST 最多再点击一次同一目标表格作用域内的新增入口
- **AND** 重试后仍未增长时，当前步骤 MUST 失败并保留首次点击和最终点击的行状态诊断

#### Scenario: 不可靠的点击前行数不得触发重试
- **WHEN** `editable_table.add_row` 的首次点击结果显示 `row_state_changed=false`
- **AND** 点击前行数来自 placeholder 按钮自身、外层表单容器、相邻表格、背景表格，或无法证明属于目标表格 root
- **THEN** 系统 MUST NOT 使用该点击前行数触发受控重试
- **AND** 如果点击后目标表格 root 已出现真实可编辑行，当前步骤 MUST 报告成功
- **AND** 如果点击后目标表格 root 仍无真实可编辑行，当前步骤 MUST 失败并输出目标 root 不可靠或未新增的诊断
