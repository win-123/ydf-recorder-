## Context

当前 `table.assert_column_values` 通过 `_TABLE_COLUMN_VALUES_SCRIPT` 从目标表格 body 中收集可见行，再按列 identity 或列索引读取目标列值。真实页面验证显示，执行项目立项列表的底部小计行 class 为 `wui-table-row tfoot-tr tfoot-tr-first tfoot-tr-background-bsubtotal`，行文本为 `小计 190,000.00`，被现有采集逻辑当作普通行处理。

同一文件中其它表格路径已经存在类似 `isSummaryRow` 过滤逻辑，能按 class 中的 `summary/footer/total/subtotal` 或文本 `小计/合计/汇总/总计` 排除汇总行。本变更应把同样的业务行判定原则引入列值断言路径。

## Goals / Non-Goals

**Goals:**

- `table.assert_column_values` 只校验真实业务数据行，不把页脚汇总、小计、合计行纳入 `values`。
- 过滤逻辑覆盖真实 WUI 表格的 `tfoot-tr`、`bsubtotal` 和中文 `小计` 文本。
- 保留已有作用域解析、header/body 分离、固定列副本和 identity 优先的列映射行为。
- 失败诊断仍能暴露目标列、目标表格 fieldid 和 headers。

**Non-Goals:**

- 不新增 DSL 参数来手动控制是否包含汇总行。
- 不改变 `table.assert_columns` 的表头集合断言语义。
- 不处理可编辑表格行定位以外的新表格编辑能力。

## Decisions

1. 在 `_TABLE_COLUMN_VALUES_SCRIPT` 内新增本地 `isSummaryRow(row)`，并在 `dataRowsForTable()` 收集 rows 时过滤。

   选择这个位置的原因是列值断言的两条读取路径都依赖 `dataRowsForTable()` 或 `relatedTableBodies()`。先过滤业务行能避免汇总行进入 identity/索引读取路径。替代方案是在 executor 端过滤返回值，但 executor 只看到字符串值，无法可靠区分业务金额和汇总金额。

2. 汇总行判定同时使用 class 和文本。

   class 规则覆盖 `summary/footer/total/subtotal/tfoot` 以及真实出现的 `bsubtotal`；文本规则覆盖整行或首个可见单元格以 `小计/合计/汇总/总计` 开头。替代方案是只判断 class，但不同渲染器和主题可能只保留中文文本，不保留稳定 class。

3. 保持过滤逻辑为内部运行时行为，不扩展 DSL。

   `table.assert_column_values` 的业务语义是断言数据行列值，默认包含汇总行会造成误判。新增参数会把本应一致的运行时规则转嫁给用例作者，且会让现有 DSL 继续失败。

## Risks / Trade-offs

- [Risk] 某些业务表格可能存在真实数据行以 `小计`、`合计` 开头。 -> Mitigation: 仅在整行或首个可见单元格呈现汇总标识，或 class 明确表示 footer/summary 时过滤；普通项目名称列包含这些词但首列不是汇总标识时不应受影响。
- [Risk] 多套表格脚本重复维护汇总行判定。 -> Mitigation: 本次先保持局部改动，避免重构扩大风险；后续若继续出现重复，可再抽取共享 JS 片段。
- [Risk] 过滤汇总行后，如果页面只有汇总行没有业务行，列值断言会变为无可验证数据。 -> Mitigation: 这符合数据行断言语义，错误应继续走现有“表格列无可验证数据”路径。
