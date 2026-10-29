## Context

当前 `editable_table.add_row` 有两层表格匹配：

- executor 先用 `target.table` 与 manifest region label 做精确语义匹配。
- runtime 再从页面 DOM 中按可见文本、附近标题和表格 root 关系选择 `新增` 入口。

真实 `非税收入缴库全景` 新增页里，用户可见分组标题是 `缴款明细信息`，manifest 可编辑表格 label 是 `缴库明细表格`，运行时表格附近只稳定暴露表头列名和 `+ 新增`。因此 DSL 写分组标题会被 executor 拦截，写模板表格名又被 runtime 拒绝；不写表格名虽然能点到 `+ 新增`，但当前步骤只按点击成功收口，后续 `fill_row` 仍可能看到 `暂无数据`。

## Goals / Non-Goals

**Goals:**

- 让 `editable_table.add_row target.table` 同时接受页面分组标题和模板表格名，只要二者能解析到同一个当前前景可编辑表格。
- 将 executor 解析出的目标表格身份传入 runtime，优先按 `table_fieldid`、列身份或目标 root 约束新增入口。
- 点击 `新增` 后确认目标表格出现真实可编辑行；失败时报告 root、行文本、空态和候选新增按钮诊断。
- 保持未指定 `target.table` 的简单用例兼容。

**Non-Goals:**

- 不为 DSL 新增 `editable_table.add_row` 语法。
- 不修复本用例后续业务字段是否应录入 `收款国库` 的问题；那属于明细列设计或用例数据问题。
- 不重写可编辑表格定位体系，只复用现有 manifest 列身份、表格 fieldid 和 runtime root 诊断。

## Decisions

1. 在 executor 中复用现有表格/列候选信息解析目标表格身份。

   `fill_row` 已能从 `current_manifest.table_columns` 推导列所属 region 和 `table_fieldid`。`add_row` 应增加一个轻量解析步骤：当 `target.table` 与 region label 不完全相等时，允许通过页面分组标题、region 邻近标签或唯一可编辑表格降级匹配，最终输出规范化的目标表格名和可用 `table_fieldid`。这比在 runtime 里扩大文本搜索更稳，也避免每个调用方重复处理同义表格名。

2. runtime 新增行优先按身份限定 root，文本标题只作为兜底。

   如果传入 `table_fieldid` 或等价目标 root 信息，`_EDITABLE_TABLE_ADD_ROW_SCRIPT` 应先在该 root 或同一可编辑表格区域内寻找 `新增`。只有缺少身份时，才保留现有可见文本和附近标题评分。这样能覆盖“页面没有显示模板表格名”的情况。

3. `add_row` 成功条件从“点击已发出”提升为“目标表格出现真实数据行”。

   当前报告里 `add_row` 成功但下一步仍命中 `暂无数据`，说明成功条件太弱。实现阶段应在点击后等待目标 root 的数据行数量增加，或至少从空态变为可编辑数据行；仍为空态时当前 `add_row` 失败，避免把根因延迟到 `fill_row`。

## Risks / Trade-offs

- 表格分组标题和模板表格名可能一对多 → 只在能解析到唯一前景可编辑表格时自动接受；多候选时失败并输出候选摘要。
- 某些页面新增行后需要异步较长时间 → 使用现有等待窗口和可配置超时风格，不引入新配置。
- 未指定 `target.table` 的旧用例可能仍点到错误新增入口 → 本 change 不扩大无表格名语义，只在指定表格时增强作用域；无表格名保留现有行为和诊断。
