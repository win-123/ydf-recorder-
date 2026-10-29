## Context

`table_row_selection.select` 已经支持在指定表格作用域内找目标行，并在没有 checkbox 时点击业务行作为 fallback。当前问题有两层：

- checkbox 分支在确认状态失败后继续点击同一行的其它候选，可能把已勾选状态再次反选。
- row-click fallback 的目标根可能来自复用的 `fieldid` 旧 DOM 或被表单覆盖的分裂表格片段，`row.click()` 的几何中心会落到错误业务字段或覆盖层，后续操作仍提示 `请选择一条调出方数据数据`。

现有相关路径包括：

- `target.row_number` / `target.first_available` 经过 `select_table_row_by_index()` 和 `_click_row_checkbox_by_index()`。
- `target.match` / `target.rows` 经过 `select_table_row()` 和 `_click_row_checkbox_by_match_values()`。
- checkbox 路径已经有明确控件状态，风险集中在无 checkbox 的 row-click fallback。

## Goals / Non-Goals

**Goals:**

- 无 checkbox 行点击必须落在真实可接收 pointer 事件的目标表格业务行上。
- 能检测到真实行选中/当前行证据时才用 `selected_after=true` 返回；页面不暴露可读选中态时允许返回成功，但必须记录 `accepted_unconfirmed=true` 和点击点诊断。
- 三条入口共用相同的 row-click 验收逻辑，避免一个路径修好另一个路径继续假成功。
- 报告中保留最小可审计诊断，能看出使用的是 checkbox 还是 row-click，以及 row-click 是否确认选中。
- 修复当前真实 YAML 中 `调出方` 行选择假成功导致 `调入方` 后续操作失败的问题。

**Non-Goals:**

- 不新增 DSL 字段，不改变 `table_row_selection.select` 的写法。
- 不引入配置化选择策略；选择证据按运行时 DOM 规则识别。
- 不改变有 checkbox 表格的优先级，仍优先点击行选择控件。
- 不把后续业务 warning 文本作为行选择成功依据；warning 只用于诊断失败后果。

## Decisions

1. 在 runtime 增加共享的 row-click 选中态验证 helper。

   `_try_click_table_row_for_selection(row)` 继续负责无 checkbox fallback，但点击前必须先确认目标行或候选单元格可以通过 `document.elementFromPoint` 接收 pointer 事件，避免命中旧 DOM、被覆盖 DOM 或 WUI 分裂表格中的错误片段。点击后读取目标行或关联行上的选中证据。候选证据优先使用稳定 DOM 语义：`aria-selected=true`、`aria-current`、常见 selected/current/active class、WUI/表格当前行 class，以及行内可读的 checked/selected 选择态。

   取舍：不为每个业务表写专用规则。真实 `调出方` 表格点击后存在视觉高亮和业务状态，但没有可读 DOM 选中证据，因此该路径记录 `accepted_unconfirmed=true`，并保留 `click_point`、`row_state` 诊断。

2. 保持 checkbox-first。

   目标行存在 checkbox 或等效选择控件时仍走 `_try_click_row_checkbox()`。checkbox 点击后只确认一次状态，不继续点击同一行其它 checkbox 候选，避免勾选后反选。row-click fallback 只在已解析表格作用域内、且没有可用选择控件时触发，避免误点可编辑单元格、链接或行级动作。

3. 让失败尽早暴露。

   如果 fieldid 命中的表格根没有可接收 pointer 的有效业务行，说明可能命中了旧 DOM 或 header-only split root，应按 `target.table` 重新解析可见根，并支持 WUI header/body 聚合。只有找不到真实可点击业务行时才失败。

4. 诊断使用已有结果通道。

   Runtime 记录最后一次表格选择诊断，例如 `strategy=checkbox|row_click`、`selected_after=true|false`、`table`、`table_fieldid`、`row_number`、`row_selector`。Executor 在 `StepResult.data` 中带出可序列化诊断即可，不新增文件格式。

## Risks / Trade-offs

- [Risk] 某些 YonDiF 表格的选中态不使用常见 class/ARIA。→ 记录 `accepted_unconfirmed=true`、点击点和 row_state，并用真实用例验证后续业务动作不再提示未选择。
- [Risk] 行点击可能只聚焦单元格而不选择业务行。→ 必须点击可接收 pointer 的真实业务行单元格，且真实用例必须越过依赖该选择的后续动作。
- [Risk] 新增等待会增加少量耗时。→ 只在无 checkbox row-click fallback 路径执行，常规 checkbox 表格不受影响。
