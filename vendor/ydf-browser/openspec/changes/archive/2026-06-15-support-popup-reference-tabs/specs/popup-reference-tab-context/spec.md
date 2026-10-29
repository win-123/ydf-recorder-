## ADDED Requirements

### Requirement: 弹出参照目标支持内部页签上下文
系统 SHALL 允许结构化弹出参照目标声明参照内部页签上下文，并在选择候选前切换到目标页签。

#### Scenario: 可编辑表格收款方户名通过本单位人员账户页签选择
- **WHEN** DSL 在 `editable_table.fill_row` 中填写 `收款方户名`，字段值包含 `tab: 本单位人员账户`、`filter: 苏康涯` 和 `match.column: 户名`
- **THEN** 运行时 MUST 打开该单元格的弹出参照，在当前参照 iframe 或弹窗根内点击 `本单位人员账户` 页签，再使用参照内通用搜索框搜索 `苏康涯`
- **AND** 运行时 MUST 在切换后的页签内容中按 `户名 = 苏康涯` 匹配表格行，选择该行，确认参照，并等待目标单元格回填
- **AND** 运行时 MUST NOT 在默认 `常用账户` 页签内直接查找 `苏康涯`

#### Scenario: 页签上下文先于树和过滤条件执行
- **WHEN** 弹出参照目标同时包含 `tab`、`tree` 和 `match`
- **THEN** 运行时 MUST 先在参照根内应用 `tab` 上下文，再应用 `tree` 上下文，最后执行过滤和候选匹配
- **AND** 页签和树上下文都 MUST 只限定候选范围，不能单独作为最终选择值

#### Scenario: 页签已激活时保持幂等
- **WHEN** 目标参照页签已经处于激活状态
- **THEN** 运行时 SHALL 记录该页签上下文并继续后续选择流程
- **AND** 运行时 MUST NOT 因重复点击已激活页签导致已选候选被清空或列表被不必要刷新

### Requirement: 弹出参照页签点击限定在当前参照根内
系统 MUST 将结构化参照目标中的 `tab` / `tabs` 点击限定在当前活动弹出参照 shell、choice root 或其 iframe context 内。

#### Scenario: 背景页面存在同名页签
- **WHEN** 背景单据页或其他区域存在与参照内部相同文本的页签
- **AND** 当前结构化参照目标声明 `tab`
- **THEN** 运行时 MUST 只在当前活动参照根内查找并点击目标页签
- **AND** 运行时 MUST NOT 调用页面级 `tab.click` 或退回全页面裸文本点击

#### Scenario: 参照内页签不存在时报错
- **WHEN** 结构化参照目标声明 `tab: 本单位人员账户`
- **AND** 当前活动参照根内不存在该页签
- **THEN** 当前步骤 MUST 失败于业务选择前
- **AND** 错误信息 MUST 包含缺失页签标签、当前参照根可见文本或可见页签候选，用于诊断目标页签是否写错或参照结构变化

### Requirement: 弹出参照页签上下文参与步骤诊断
系统 SHALL 在通过弹出参照页签上下文完成选择时，将页签上下文写入步骤结果或字段级诊断。

#### Scenario: form/query/popup_reference 报告页签上下文
- **WHEN** `form.fill`、`query.search` 或 `popup_reference.select` 的结构化参照目标包含 `tab`
- **THEN** 对应步骤结果 MUST 保留原有 `selected`、`confirmed`、`confirm_label` 和 `popup_tree_context` 诊断
- **AND** 步骤结果 MUST 增加 `popup_tab_context`，记录已应用的参照页签标签

#### Scenario: editable_table.fill_row 报告单元格参照页签上下文
- **WHEN** `editable_table.fill_row` 成功录入带 `tab` 的可编辑表格参照列
- **THEN** 字段级结果 MUST 保留原有 `column`、`value`、列身份和定位来源诊断
- **AND** 字段级结果 MUST 包含 `popup_tab_context`，并在运行时返回时透传 `selected`、`confirmed`、`confirm_label` 或 `popup_tree_context` 中存在的诊断字段

### Requirement: 标量 filter 支持无标签通用搜索框
系统 SHALL 在弹出参照目标使用标量 `filter` 时，将其解释为参照内通用关键字搜索，而不是要求存在同名查询字段标签。

#### Scenario: 使用通用搜索框搜索收款方户名
- **WHEN** 弹出参照目标包含 `filter: 苏康涯`
- **AND** 当前参照根内存在 placeholder 为 `输入关键字搜索`、`搜索`、`关键字`、`查询` 或等价语义的输入框
- **THEN** 运行时 MUST 在该输入框内填写 `苏康涯` 并触发参照候选刷新
- **AND** 运行时 MUST NOT 报告 `未找到弹出参照查询字段: 收款方户名`

#### Scenario: filter.conditions 保持带标签查询字段语义
- **WHEN** 弹出参照目标包含 `filter.conditions`
- **THEN** 运行时 SHALL 继续按条件中的 `field` 查找参照内带标签查询字段并填写
- **AND** 如果目标参照只有通用关键字搜索框且没有该标签字段，运行时 MUST 给出明确失败，提示可改用标量 `filter`
