## Context

`table_row_action.click` 目前只描述“先聚焦表格行，再点击该行露出的按钮”。对 `target.row_number`，executor 调用 runtime 的 `focus_table_row_by_index(row_number)`，该调用没有表格名、`table_fieldid` 或列清单，因此只能在全页面可见数据行中找第 N 行。

真实失败链路是 `领用分配 -> 未分配 -> 分配 -> 物资信息`：`editable_table.fill_row` 已成功定位到 `物资信息` 子表，并在报告中输出 `table_fieldid=wzxx_table`，但后续 `table_row_action.click target.action=选择库存 target.row_number=1` 没有表格作用域，导致点击按钮前的行聚焦失败。

现有代码已经有可复用的表格作用域能力：`table_row_selection.select`、`table.assert_*` 和 `editable_table.fill_row` 都能解析 `target.table`、传递 `table_fieldid`，runtime 也已有 `_table_selection_context` 和按表格 fieldid 限定 root 的逻辑。本变更应复用这些能力。

## Goals / Non-Goals

**Goals:**

- 允许 `table_row_action.click` 使用 `target.table` / `target.table_name` 指定目标表格。
- 当 `table_row_action.click` 紧接在成功的 `editable_table.fill_row` 后且未显式指定表格时，复用该可编辑表格的作用域。
- 在指定表格后，按 `row_number` 或 `match` 只在目标表格内聚焦业务行。
- 点击行级按钮前重新捕获 runtime DOM，保持既有 hover 后绑定行按钮的行为。
- 步骤结果和失败诊断包含 `table`、可用时的 `table_fieldid` 和行定位信息。
- 让真实用例中的 `物资信息` 子表 `选择库存` 能通过行级按钮语义点击。

**Non-Goals:**

- 不新增新的组件语义，例如 `editable_table_row_action.click`。
- 不改变 `toolbar.click`、`action.click` 或 `editable_table.fill_row` 的 DSL。
- 不把未指定 `target.table` 的所有旧用例强制失败；单主表和历史主列表场景继续兼容。
- 不跨越弹窗确认、工具栏点击、页签切换等其它业务步骤长期保留隐式表格作用域。

## Decisions

1. `table_row_action.click` 直接支持 `target.table`。

   这比新增组件更小，也和 `table_row_selection.select`、`table.assert_*` 的 DSL 保持一致。`table_name` 作为别名兼容已有表格 DSL 风格。

2. executor 复用主表作用域解析，并在可编辑表格场景补充目标表格解析。

   对普通列表页，复用 `_resolve_main_table_fieldid`、`_resolve_main_table_column_labels`。对编辑页子表，复用可编辑表格区域解析，取得 `table_fieldid` 和列清单。这样不需要新建一套模板扫描逻辑。

3. runtime 增加作用域化的行聚焦能力，而不是改按钮点击 selector。

   当前失败发生在点击按钮前的 `focus_table_row_by_index`，按钮元数据和运行时文本都已存在。正确修复点是让 `focus_table_row_by_index` / `focus_table_row` 接收 `table`、`table_fieldid`、`table_columns`，并复用 `_table_selection_context` 限定行搜索范围。

4. 未指定 `target.table` 时保留兼容。

   旧用例大量依赖主表第 N 行语义；本变更只在用户显式指定表格，或紧邻前序可编辑表格录入时收窄作用域。后续如果要做更宽泛的自动歧义检测，可以另开 change。

5. 允许紧邻前序可编辑表格录入的最小隐式作用域。

   真实失败 YAML 已经在前一步 `editable_table.fill_row target.table=物资信息` 中解析出 `table_fieldid=wzxx_table`，下一步立即执行 `table_row_action.click target.row_number=1`。这不是跨页面猜测，而是同一编辑页、相邻步骤之间的行按钮操作。实现只记录最近一次成功的可编辑表格作用域，并在下一次行按钮点击消耗它；其它会改变页面上下文的步骤不使用这个隐式作用域。

## Risks / Trade-offs

- [Risk] 子表不是主表 manifest 区域，单纯主表解析可能拿不到 `wzxx_table`。  
  Mitigation: 实现阶段同时覆盖 main table 和 editable table region 的表格作用域解析，优先使用 DSL 指定表名精确匹配。

- [Risk] 行聚焦限定到表格 root 后，WUI header/body 分离导致 root 内没有 body。  
  Mitigation: 复用 `_table_selection_context` 及其 fieldid root 聚合能力，它已经服务于表格选择和断言。

- [Risk] 行按钮可能渲染在行外浮层中，严格限制按钮 selector 到表格 root 可能误伤。  
  Mitigation: 本变更只限定“行聚焦”范围；按钮点击仍使用现有 hover 后可见行级动作解析，避免过早收窄。

- [Risk] 隐式沿用上一条 `editable_table.fill_row` 的表格可能跨步骤误选。  
  Mitigation: 只在紧邻的 `table_row_action.click` 中消费最近一次成功可编辑表格作用域；显式 `target.table` 始终优先，任何其它业务步骤都会自然覆盖或不使用该作用域。
