## Context

`table_row_selection.select` 当前先从 DSL `match` 中抽取匹配值，再调用 runtime 定位行并点击行选择控件。问题点有两个：单条件 `equals: "是"` 会走整行文本包含查找，无法保证值来自 `政府采购标识` 列；同时单位资金代管预算支付全景页面存在 `可用指标` 和 `表格` 两张主表，业务内容在服务 iframe 内，裸查 `tbody tr` 会丢失正确作用域。

## Goals / Non-Goals

**Goals:**
- `target.match.column + equals` 必须按目标列精确定位数据行。
- 未显式写 `target.table` 时，如果目标列只属于一张主表，executor 应把该表解析为选择作用域并传给 runtime。
- 匹配到业务行后，仍复用现有行选择控件点击逻辑，不改变 DSL 写法。
- 失败信息能说明是表格作用域、列匹配、行匹配还是选择控件问题。

**Non-Goals:**
- 不新增 `table_row_selection` DSL 字段。
- 不改变 `target.select_all`、`row_number(s)`、`rows` 的语义。
- 不把 `政府采购标识` 这类文本列当成 checkbox 字段处理。
- 不为单位资金页面写硬编码菜单、表名或列名特例。

## Decisions

1. 在 executor 层复用现有表格列归属解析。
   - 当 DSL 写了 `target.table`，继续使用显式表格。
   - 当 DSL 未写 `target.table`，但 `target.match.column` 只出现在一张主表中，自动传递该表的 `table_fieldid` 和 `table_columns`。
   - 当目标列在多张表中都存在且没有更多上下文时，失败并提示补充 `target.table`。

2. 在 runtime 层把单条件匹配也走列值读取路径。
   - 当前单值分支直接调用 `_click_row_checkbox_by_text()`，会误把 `是` 当整行文本条件。
   - 修复后，只要存在 `column`，就用表头到单元格的映射读取该列值，值匹配后再点击同行选择控件。
   - 没有 `column` 的旧 DSL 保持整行文本包含兜底。

3. 点击选择控件仍复用现有 `_try_click_row_checkbox()`。
   - 这样最小化改动面，避免重新定义行选择控件。
   - 只在找到行但没有 checkbox 时补充更清晰诊断；不引入“点击整行即选择”的新通用规则。

## Risks / Trade-offs

- [Risk] 自动按列推断表格可能在同名列页面上拒绝执行旧用例。→ Mitigation: 只在唯一列归属时自动限定；歧义时要求 `target.table`，不做猜测。
- [Risk] 某些 WUI 表格 header/body 分离导致列值读取失败。→ Mitigation: 复用已有 header/body 关联和表格 root 解析路径，新增覆盖单位资金页面的诊断用例。
- [Risk] 旧用例依赖整行文本包含偶然命中。→ Mitigation: 仅 `match.column` 存在时启用列精确匹配；无列名写法保留原行为。
