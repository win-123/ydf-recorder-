## Why

`预算编制` 用例在选择会计科目后需要勾选当前表格全部候选行。当前 `table_row_selection.select` 只能按 `match`、`rows`、`row_number`、`row_numbers` 或 `first_available` 勾选数据行，无法表达“点击表头 checkbox 全选”的业务意图，只能临时写成 `row_number: 1`，导致用例语义与真实操作不一致。

表格第一列为 checkbox 时，表头同列 checkbox 是 YonDiF 页面已有的批量选择入口；DSL 需要直接表达这个入口，并让运行时在正确表格作用域内执行全选。

## What Changes

- 扩展 `table_row_selection.select` 目标语义，新增 `target.select_all: true` 表示点击表头 checkbox 以选中当前表格全部可选行。
- 多表格页面继续复用现有 `target.table` 作用域规则；未指定表格且存在多张可见主表格时，应在业务点击前失败并提示补充 `target.table`。
- 运行时应优先在解析出的表格根内定位表头 checkbox，不得把数据行 checkbox 或页面其他 checkbox 当作全选入口。
- `select_all` 应按“确保全选”执行：已全选时不重复点击反选；未选中或半选状态时点击表头 checkbox。
- 补充 DSL 校验、文档、示例和回归测试，覆盖单表全选、多表指定表格全选、缺少表头 checkbox 的失败场景。

## Capabilities

### New Capabilities

- `table-row-selection`: 描述表格行选择 DSL 的数据行勾选、多行勾选和表头全选语义。

### Modified Capabilities

- 无。

## Impact

- 影响 DSL 校验、executor 分流、Playwright runtime 表格选择逻辑、DSL 文档、示例 YAML 和相关测试。
- 主要涉及 `ydf_browser/dsl.py`、`ydf_browser/executor.py`、`ydf_browser/runtime.py`、`skills/gov-ydfdev-browser/references/dsl-reference.md`、`docs/action-capability-test-plan.md` 和 `tests/`。
- 不引入新外部依赖，不改变 `row_number` 的 1-based 语义，不改变 `match`、`rows`、`row_numbers` 或 `first_available` 的既有行为。
