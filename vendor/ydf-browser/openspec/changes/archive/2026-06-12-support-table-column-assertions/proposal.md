## Why

`预算绩效>>绩效模板>>模板库` 的新增表单需要验证明细表“三级模板明细”不再展示 `一级绩效指标分值` 和 `二级绩效指标分值` 两列。当前 `table.assert_column_values`、`table.assert_row_values` 和 `table.assert_empty` 都面向表格数据值，无法表达“表头列不存在”的结构性断言，尤其在空表场景下会把“列存在但无数据”和“列不存在”混在一起。

ydf-browser 的 DSL 应继续描述 YonDiF 单据页语义，而不是暴露 `locator/get_table_headers` 这类底层浏览器动作；因此需要新增明确的表格列集合断言。

## What Changes

- 新增 `table.assert_columns` 组件操作，用于断言当前表格的表头列集合。
- `target.table` 用于限定目标表格，例如 `三级模板明细`；多表格页面未指定表格且无法唯一确定作用域时，应在业务断言前失败。
- `target.present` 表达必须存在的列，`target.absent` 表达必须不存在的列；二者至少填写一个，可同时填写。
- 列名匹配应采用精确归一化：去掉前置必填星号和空白，但不做包含匹配，避免 `一级绩效指标` 与 `一级绩效指标分值` 这类前缀关系误判。
- 运行时应读取目标表格真实 DOM 表头，并在横向滚动表格中采集所有可到达列头；模板 `manifest.table_columns` 只作为作用域解析和诊断辅助。
- 断言失败时报告实际采集到的 `headers`，并明确列出缺失的必需列或不应存在的列。

## Capabilities

### New Capabilities

- `table-column-assertions`: 描述表格表头列集合断言 DSL，包括必须存在列、必须不存在列、表格作用域和失败诊断。

### Modified Capabilities

- 无。

## Impact

- 影响 DSL 校验、executor 表格断言分流、Playwright runtime 表头采集、DSL 文档、动作能力测试文档、示例 YAML 和相关测试。
- 主要涉及 `ydf_browser/dsl.py`、`ydf_browser/executor.py`、`ydf_browser/runtime.py`、`skills/gov-ydfdev-browser/references/dsl-reference.md`、`docs/action-capability-test-plan.md`、`tests/` 和目标用例 YAML。
- 不引入新外部依赖，不改变现有 `table.assert_column_values`、`table.assert_row_values`、`table.assert_empty` 的数据值断言语义。
