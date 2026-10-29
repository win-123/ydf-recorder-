## Why

`table_row_action.click` 当前按 `row_number` 定位时只在全页面查找第 N 条可见数据行，无法限定到分配页、编辑页或弹窗中的目标子表。真实用例 `实物管理-易耗品物资-领用分配-未分配页签分配-0001 (1).yaml` 已复现：`物资信息` 子表中存在 `选择库存` 行按钮，但步骤在点击按钮前失败为未找到表格行。

## What Changes

- 为 `table_row_action.click` 增加表格作用域语义，支持 DSL 通过 `target.table` 指定目标表格。
- 当 `table_row_action.click` 未显式指定表格、且紧邻前序成功的 `editable_table.fill_row` 已解析出目标表格时，复用该表格作用域执行行按钮定位。
- executor 需要将 `target.table` 解析为表格 `fieldid` 和列清单，并把作用域传给 runtime 的行聚焦逻辑。
- runtime 需要在指定表格作用域内按 `row_number` 或 `match` 聚焦目标行，然后点击该行露出的行级按钮。
- 保持未指定 `target.table` 的既有主表行按钮用例兼容；只有存在多表歧义或目标行无法在作用域内解析时失败。
- 不引入新的通用按钮查找框架，不改变 `toolbar.click`、`editable_table.fill_row` 或 `table_row_selection.select` 的既有 DSL 语义。

## Capabilities

### New Capabilities
- `table-row-action-clicking`: 约束表格行级按钮点击的行定位、表格作用域、DSL 校验和诊断输出。

### Modified Capabilities

## Impact

- 影响 DSL schema：`table_row_action.click target` 允许 `table` / `table_name`。
- 影响 executor：行级按钮点击前的行定位需要解析、记忆并传递表格作用域。
- 影响 runtime：按行号或匹配条件聚焦行时需要支持 `table`、`table_fieldid`、`table_columns`。
- 影响测试：新增 executor/runtime/DSL 回归，并用真实 YAML 验证 `物资信息` 子表 `选择库存` 按钮可点击。
