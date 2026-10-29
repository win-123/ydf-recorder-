## Context

`table_row_selection.select` 的执行链路会先由 executor 根据当前 manifest 把 `target.table: 调出方` 解析为 `table_fieldid=table1`，再由 runtime 在页面 DOM 中查找 `table1_drag` / `table1` 对应的表格根。

当前 runtime 为兼容 WUI 表格表头和表体分裂，会全页面、全 frame 收集同 fieldid 候选并聚合成 table cluster，然后按 `columnsMatched`、`selectableRows` 等指标排序。这个流程仍在 fieldid 候选集合内，但当动态模板切换后背景旧表和前景新表存在相同 fieldid 时，背景旧根可能因为有 checkbox / `selectableRows` 排序靠前；后续按行号选择时，该根内行被前景层覆盖或不可接收 pointer 事件，于是报告 `当前可见有效行数=0`。

已有无 checkbox 行点击兜底只在 runtime 找到有效业务行后才会执行。本 change 的根因不是 DSL 表名未匹配，也不是无 checkbox 兜底缺失，而是 fieldid 根候选在进入行扫描前选错了实际前景根。

## Goals / Non-Goals

**Goals:**

- 在 `table_fieldid` 已解析成功时，只在该 fieldid 对应 DOM 候选内选择表格根，不按 `target.table` 文本回退到其它根。
- 让同 fieldid 候选排序优先当前前景、可见、包含可接收 pointer 事件业务行的表格根。
- 保留 WUI 表头/表体分裂 DOM 聚合、checkbox 优先点击、无 checkbox 行点击兜底和现有失败诊断。
- 用聚焦测试复现背景旧根有 `selectableRows`、前景真实根无 checkbox 但有可接收业务行的场景，并用真实 DSL 验证。

**Non-Goals:**

- 不修改 DSL schema 或用户写法。
- 不新增页面专用分支，不把待分预算管理页面做成特例。
- 不重做表格列匹配、树形表格展开、表格行断言或 editable table 语义。
- 不改变 `target.table` 未能解析为 manifest fieldid 时的既有表名匹配行为。

## Decisions

- 在 `_resolve_table_selection_fieldid_root_selector()` 对应的 fieldid 根候选脚本中补充前景业务行信号。相比在 `_click_row_checkbox_by_index()` 失败后再二次查找，这能在进入行扫描前选中正确根，避免补丁变成“失败后猜另一个表”。
- `receivableRows` 或等价信号应基于真实可见业务行和 `elementFromPoint` 可接收 pointer 事件判断。相比只看 `selectableRows`，这个信号能区分前景真实表格和背景旧 DOM。
- `selectableRows` 继续保留为同等前景候选内的辅助排序项，不能压过“有可接收业务行”。这样 checkbox 表格仍优先点击 checkbox，但无 checkbox 前景表不会被背景 checkbox 表抢走。
- fieldid 成功解析后不使用 `target.table` 文本重新全局匹配。表名只用于 executor 找到 manifest region；runtime 阶段的强身份是 `table_fieldid`。
- 测试优先覆盖根选择结果和点击行为：背景候选不能被点击，前景无 checkbox 行必须进入 row-click 兜底并带出 `selection_debug`。

## Risks / Trade-offs

- 前景业务行检测依赖 `elementFromPoint`，遇到页面动画或短暂遮罩时可能判断为不可接收 → 复用现有等待节奏，不在本 change 中新增长轮询；真实 DSL 仍失败时再根据报告证据处理等待问题。
- 有些表格只有 checkbox 可接收 pointer，普通单元格不可接收 → `selectableRows` 仍作为辅助信号保留，避免破坏 checkbox-first 行选择。
- fieldid 候选中表头/表体分裂可能导致业务行信号被算在 body 根而不是 header 根 → 继续使用现有 `splitTableClusterRoot()` 聚合后再计算候选指标。
- 失败诊断可能需要暴露更多候选摘要才能定位同 fieldid 冲突 → 先保留现有根摘要，必要时补充候选数量和前景业务行计数，不输出完整 DOM。
