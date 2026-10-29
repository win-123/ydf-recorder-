## Why

`集中支付全景` 的 `table_row_selection.select` 在 `政府采购标识=否` 的行真实存在且可勾选时仍失败。近期的按列值选择修复已经能推断到 `可用指标` 表，但 WUI 表格中表头 `fieldid` 与行单元格 `data-index` 不完全相同，导致列值读取不到目标单元格。

## What Changes

- 修正 `table_row_selection.select target.match.column + equals` 在 WUI 表格中的列身份匹配。
- 让运行时能把模板列 `fieldid` 与真实行单元格 `data-index` / `data-field` 关联起来，而不是只依赖相同 DOM 属性或脆弱的可见 cell 索引。
- 保持现有 DSL 写法、表格作用域推断和 checkbox 点击语义不变。

## Capabilities

### New Capabilities

### Modified Capabilities
- `table-row-selection`: 按列值选择表格行时，WUI 表格的模板列身份和运行时行单元格身份必须能正确对齐。

## Impact

- 影响代码：`ydf_browser/runtime.py` 的表格列值定位脚本。
- 影响测试：补充 WUI 表格列身份不完全一致时的行选择回归。
- 不新增依赖，不改变 DSL schema。
