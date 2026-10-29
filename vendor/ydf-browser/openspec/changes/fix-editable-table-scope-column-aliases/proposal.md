## Why

`editable_table.fill_row` 会在表格作用域预校验阶段直接比较 DSL 业务列名与 DOM 展示表头；当模板列 `物资分类`、`入库数量` 分别显示为 `物资类型`、`数量` 时，系统错误报告“缺少必需列”，导致既有真实流程在进入单元格录入前回归失败。

## What Changes

- 表格作用域预校验识别同一模板列的 `label`、`title`、`dataField` 和 `displayName` 为等价列名。
- 仅由 `editable_table.fill_row` 显式启用列别名，其他共享表格动作继续按原有精确列名校验。
- 继续按每个当前 DOM 表根独立校验表头，不把一张表的模板列或展示列借给另一张表。
- 同一个运行时表头只能满足一个必需列；真实 DOM 根即使未渲染表头，也视为已完成空表头观测。
- 增加最小单元回归和真实失败衍生 DSL，覆盖 `物资分类 → 物资类型`、`入库数量 → 数量`。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `editable-table-cell-entry`: 补充可编辑表格作用域预校验对模板业务列名与运行时展示表头别名的匹配要求，并保持多表根严格失败边界。

## Impact

- 影响 `ydf_browser/table_scope.py` 的共享必需列预校验逻辑、`ydf_browser/runtime.py` 的表头观测证据和 `ydf_browser/executor.py` 的可编辑表格调用参数。
- 增加 `tests/test_table_scope.py`、`tests/test_runtime.py` 聚焦回归和 `tests/real_cases/` 真实页面回归 DSL。
- 不增加依赖，不改变 DSL schema，也不放宽跨表格作用域匹配。
