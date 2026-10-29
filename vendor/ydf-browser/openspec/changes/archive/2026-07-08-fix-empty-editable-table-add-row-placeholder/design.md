## Context

`editable_table.add_row` 由 executor 将 `target.table` 解析为模板表格身份，再把 `table_fieldid` 和列身份交给 runtime。runtime 在页面中选择 `新增` 候选，点击后读取目标表格行状态；7 月 8 日的重复新增修复允许“非空表格首次点击未增长”时受控重试一次。

本次预算管理真实用例中，`target.table=调入方` 正确解析为 `table_fieldid=table2`。页面初始是空目标表格，新增入口渲染为 `.ydf-table-placeholder-add-button`。运行时点击该 placeholder 后实际新增了行，但行状态诊断最终显示 `before_rows=2; after_rows=2; retry_count=1`，说明验证 root 或重试门禁把空表格首次新增误判为非空表格未增长。

## Goals / Non-Goals

**Goals:**

- 让空目标表格 placeholder 首次新增后出现真实数据行时直接成功。
- 确保新增后的行状态验证限定在目标表格 root，而不是 placeholder 按钮自身、外层表单容器或相邻表格。
- 保留非空目标表格首次点击未增长时的一次受控重试。
- 失败时输出足够诊断，能看出目标表格身份、候选入口、首次点击和最终点击的行状态。

**Non-Goals:**

- 不新增 DSL 字段或改变 `target.table` 写法。
- 不放宽“新增后必须出现真实可编辑数据行”的成功标准。
- 不为预算管理页面、`调入方` 或 `table2` 写专用分支。
- 不处理业务校验拒绝新增或页面数据缺失导致的真实失败。

## Decisions

1. 修复放在 `PlaywrightRuntime.add_editable_table_row` 和 `_EDITABLE_TABLE_ADD_ROW_SCRIPT` 的共享入口。

   所有 `editable_table.add_row` 都经过这里。放在 DSL、executor 或预算管理页面特例里会漏掉同类空态 placeholder 表格。

2. placeholder 候选只能作为点击入口，不能直接作为行状态验证 root。

   `.ydf-table-placeholder-add-button` 的文本和几何只证明它是可点击入口，不证明它是目标表格数据区。运行时应在点击前后按 `table_fieldid`、目标列身份或同一表格 cluster 重新解析目标 root；无法唯一确认时失败并报告诊断，而不是使用外层或相邻表格行数。

3. 重试只在“点击前目标 root 可靠且已有真实数据行”时启用。

   现有重试能力解决的是非空表格中上一轮编辑态吞掉首次点击的问题。空表格 placeholder 首次新增是另一种状态：点击前没有真实数据行，点击后出现第一行时应成功；如果点击后仍没有行，应失败或输出空态诊断，不应再点一次 placeholder。

4. 保留行数增长门禁。

   对非空目标表格，点击后行数不增长仍然是失败信号。修复只避免错误采样和错误重试，不把“未增长”当成功。

## Risks / Trade-offs

- 目标 root 解析更严格可能暴露之前被外层容器行数掩盖的失败 -> 这是正确失败，诊断需包含目标 fieldid 和候选 root 摘要。
- 空态表格 DOM 在点击后可能整体重渲染 -> 点击后重新按目标身份解析 root，不复用点击前的 placeholder 节点。
- 少数页面没有稳定 `table_fieldid` DOM 属性 -> 保留列身份和同一表格 cluster 兜底；仍无法唯一确认时失败，避免误判成功。
