## Context

`table_row_selection.select` 的 executor 会把 `target.table` 解析成当前 manifest 中的 `table_fieldid`，再传给 runtime 限定选行作用域。当前 runtime 的 `_table_selection_context()` 在 `table_fieldid` 命中但该根下没有可接收选择的业务行时，会继续按 `target.table` 文本重新解析表格根。

这个回退曾用于兼容 WUI 表格 header/body 分离或旧根节点命中问题，但它会破坏已解析 `table_fieldid` 的身份约束：DSL 声明在表格 A 中选行，runtime 可以在表格 B 中成功点击，报告还只记录 DSL 目标而非实际 DOM 根。

## Goals / Non-Goals

**Goals:**
- 已传入 `table_fieldid` 时，将它作为 `table_row_selection.select` 的硬作用域。
- fieldid 根缺失、不可见或没有可选业务行时，在点击前失败并给出诊断。
- 成功选行时，在步骤结果中记录 runtime 实际命中的表格根摘要，便于审计是否真的点在目标表格内。

**Non-Goals:**
- 不改变 DSL schema。
- 不放宽 executor 对 `target.table` 的 manifest 匹配规则。
- 不统一改造 `capture_row_values`、`editable_table`、`table_row_action` 等其它表格操作。
- 不移除 WUI header/body 分离聚合能力；只禁止 fieldid 已解析后退回到另一个按文本命中的表格。

## Decisions

- 在 runtime 层移除 `table_fieldid` 命中后按 `table` 文本回退的路径。原因是 executor 已经完成语义解析，runtime 不应再用弱文本匹配覆盖强身份。
- 保留 `_resolve_table_selection_fieldid_root_selector()` 内部的 header/body 聚合。该逻辑仍服务于同一个 fieldid 表格根，不属于跨表格回退。
- 选行成功后复用 `last_table_selection_root` / `last_table_selection_debug` 输出实际根摘要。最小字段包括 root `fieldid`、`source`、`selectableRows`，可继续保留现有行号、选择器和选中状态。
- 对旧场景不做兼容开关。依赖回退才能通过的用例应暴露为失败，由 DSL 或模板绑定修正。

## Risks / Trade-offs

- [Risk] 某些旧页面 fieldid 只能命中 header，body 不在同一 DOM 根内。 -> Mitigation: 保留现有 split header/body 聚合，只要能从 fieldid 找到对应 body 仍应通过。
- [Risk] 旧 DSL 原来靠文本回退误打误撞通过。 -> Mitigation: 这是目标行为，失败信息必须带出 `table`、`table_fieldid` 和表格根摘要，便于修正用例。
- [Risk] 成功报告增加字段影响断言。 -> Mitigation: 只在 `data.selection_debug` 或等价诊断对象中追加字段，不改变既有顶层 `table`、`table_fieldid`、`row_numbers`。
