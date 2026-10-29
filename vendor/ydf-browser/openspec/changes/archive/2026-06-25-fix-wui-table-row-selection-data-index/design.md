## Context

`table_row_selection.select` 现在已经能在未写 `target.table` 时，通过 `target.match.column` 推断唯一表格作用域。当前失败发生在更底层：运行时进入了 `kyzb_table`，也识别到可选择数据行，但 `_TABLE_ROW_VALUES_SCRIPT` 没有把 `政府采购标识` 表头映射到真实行单元格。

真实 DOM 中表头是 `fieldid=kyzb_table_isGovPurName`，行单元格是 `data-index=isGovPurName`。两者表达同一模板列，但不是完全相同字符串。当前脚本只支持完全相同的 DOM identity，失败后按可见 cell 索引兜底；WUI 表格的业务单元格会渲染外层 cell、内部 wrapper 和文本节点多个可见 cell，索引兜底不可靠。

## Goals / Non-Goals

**Goals:**
- 让 `target.match.column + equals` 能在 WUI 表格中用模板列 identity 找到对应数据单元格。
- 复用现有 `table_columns`、模板列 `fieldid`、行单元格 `data-index` / `data-field`，不增加 DSL。
- 保持找到业务行后复用现有行 checkbox 点击逻辑。
- 补一个最小回归覆盖真实 DOM 形态：表头 `fieldid` 带表格前缀，行单元格 `data-index` 使用裸数据字段，且一列有多个可见子节点。

**Non-Goals:**
- 不新增 `target.data_field`、`target.fieldid` 等 DSL 字段。
- 不把 `政府采购标识` 文本列当作 checkbox。
- 不为 `集中支付全景`、`kyzb_table` 或 `isGovPurName` 写页面特例。

## Decisions

1. 在运行时列匹配脚本内增强 identity 对齐。
   - 表头 identity 继续读取 `fieldid`、`data-fieldid`、`data-index` 等属性。
   - 行单元格 identity 继续读取 `data-index`、`data-field` 等属性。
   - 当表头 identity 以表格前缀加下划线结尾包含行单元格 identity，例如 `kyzb_table_isGovPurName` 对 `isGovPurName`，视为同一列。
   - 这是最小修复点：已有失败正落在 `_TABLE_ROW_VALUES_SCRIPT`，不需要改 executor。

2. 索引兜底保留但不扩大。
   - 对没有 identity 的普通表格，仍可按现有 header index 兜底。
   - 对有 identity 的 WUI 表格，优先用 identity，避免一列多个可见子节点导致索引偏移。

3. 测试使用脚本级 DOM 回归。
   - 直接构造接近真实 WUI 的 header/body DOM，验证 `政府采购标识=否` 能命中行。
   - 不引入浏览器真实页面 fixtures；真实 YAML 作为最终验证。

## Risks / Trade-offs

- [Risk] 后缀匹配过宽可能把无关列错配。→ Mitigation: 仅在完整 token 边界匹配，例如 `prefix_identity` 的末段等于单元格 identity；仍优先完全相等。
- [Risk] 其它 WUI 页面使用不同属性名。→ Mitigation: 保留现有属性集合，必要时后续再按真实 DOM 扩展，不提前泛化。
