## Context

`table_row_selection.select` 当前只表达“定位数据行并勾选该行第一列 checkbox”。相关路径已经分层清晰：DSL 校验限定可用 target，executor 负责把 `match`、`rows`、`row_number`、`row_numbers` 分流到运行时，Playwright runtime 再按当前表格根查找数据行 checkbox。

本次需求来自 `预算编制` 用例中的“勾选全部”。真实页面第一列是 checkbox，表头同列 checkbox 才是批量选择入口。继续用 `row_number: 1` 会误表达为只选择第一条数据；把表头 checkbox 混入数据行计数也会破坏已有多表格行号选择的稳定性。

## Goals / Non-Goals

**Goals:**

- 为 `table_row_selection.select` 增加 `target.select_all: true`，直接表达点击表头 checkbox 全选。
- 复用现有 `target.table` 和 `table_fieldid/table_columns` 表格根解析能力，避免跨表格误选。
- 运行时只在表头区域寻找全选 checkbox，并按“确保全选”语义避免重复点击导致反选。
- 补齐 DSL 校验、executor 单元测试、runtime 单元测试、文档和示例。

**Non-Goals:**

- 不实现跨分页、跨虚拟滚动全量数据选择；本能力只触发当前 YonDiF 表格组件表头 checkbox 的原生行为。
- 不改变 `row_number` 的 1-based 语义，也不允许 `row_number: 0` 表达表头。
- 不改变已有 `match`、`rows`、`row_numbers`、`first_available` 行选择行为。
- 不新增独立组件或新的 `operation`。

## Decisions

1. DSL 使用 `select_all: true`，而不是 `all: true` 或 `row_number: 0`。

   `select_all` 与 `select_first_available` 的命名风格一致，也比 `all` 更明确。`row_number: 0` 会破坏已有“行号从 1 开始”的错误提示，并且容易把表头当成特殊数据行。

2. `select_all` 是独立定位方式，应与 `match`、`rows`、`row_number`、`row_numbers`、`row_index`、`first_available`、`select_first_available` 互斥。

   这样 executor 可以在业务动作前明确分流，不会出现“既想全选又想按条件选择”的歧义。校验错误应直接说明这些 target 字段不能混用。

3. executor 在解析表格作用域后优先处理 `select_all`，再处理现有行选择分支。

   这样 `target.table + select_all` 能拿到与行号选择一致的 `table_fieldid` 和 `table_columns`，并复用多表格歧义检测。单表格页面允许省略 `target.table`；多张可见主表格时继续要求显式表格名。

4. runtime 新增 `select_all_table_rows(...)`，内部复用 `_table_selection_context(...)`。

   该方法只在解析出的表格根内查找表头 checkbox 候选，例如 `thead input[type="checkbox"]`、表头单元格内的 `[role="checkbox"]`、常见 checkbox wrapper。若当前表格根是 `_drag` 容器，查找仍限定在该根内，但优先 `thead` / header 区，不回落到 `tbody` 数据行。

5. 表头 checkbox 点击应是幂等的“确保全选”。

   runtime 需要先判断候选是否已处于 checked 状态，包括原生 `input.checked`、`aria-checked="true"`、以及常见 checked class。已全选时直接成功；未选中或 `aria-checked="mixed"` 时点击可接收 pointer event 的表头 checkbox 或其 wrapper。点击后应等待短暂稳定时间。

## Risks / Trade-offs

- [Risk] 不同表格框架的表头 checkbox DOM 形态不完全一致。→ Mitigation: 候选选择器覆盖原生 input、role checkbox、wui/ant/u checkbox wrapper，并以表头区域作用域限制误点。
- [Risk] 部分业务表头 checkbox 表示“当前页全选”而不是“所有查询结果全选”。→ Mitigation: spec 明确本能力只触发表格组件原生表头 checkbox 行为，不承诺跨分页全选。
- [Risk] 已全选状态识别不全可能导致重复点击反选。→ Mitigation: 优先读取 input/aria/class 状态；不能可靠确认 checked 时只对 unchecked/mixed 候选点击，并用单元测试覆盖常见状态。
- [Risk] 多表格页面省略 `target.table` 会误选其他表格。→ Mitigation: 复用现有多表格歧义检测，要求业务点击前失败并列出当前表格。
