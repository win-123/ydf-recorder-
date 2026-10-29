## Why

`table_row_selection.select` 在 executor 已解析出 `table_fieldid` 后，runtime 仍可能因该 fieldid 根下未识别到可选行而回退到 `target.table` 文本重新找表格。这会造成 DSL 声明在表格 A 中选行，但实际在表格 B 中点击成功，报告还只复述目标表格，难以发现错选。

## What Changes

- 收紧 `table_row_selection.select` 的表格作用域：只要 executor 已传入 `table_fieldid`，runtime MUST 将该 fieldid 作为硬作用域。
- 找不到该 fieldid 根、或该根下没有可选业务行时，步骤 MUST 失败并输出作用域诊断，不能回退到按 `target.table` 文本搜索其它表格。
- 成功选行时，步骤结果 MUST 记录 runtime 实际命中的表格根摘要，包括可用的 root `fieldid`、`source` 和 `selectableRows`。
- **BREAKING**: 依赖旧的 `fieldid` 失败后按表名回退的用例将改为失败，需要修正模板绑定或 DSL 表格名。

## Capabilities

### New Capabilities

### Modified Capabilities
- `table-row-selection`: 修改已解析 `table_fieldid` 时的 runtime 作用域要求，并补充实际命中表格根的报告证据。

## Impact

- 影响 `ydf_browser/runtime.py` 的表格行选择作用域解析和选行诊断。
- 影响 `ydf_browser/executor.py` 的步骤结果诊断附加逻辑。
- 影响 `tests/test_runtime.py` / `tests/test_executor.py` 中表格行选择相关回归。
- 不改变 DSL schema，不新增依赖。
