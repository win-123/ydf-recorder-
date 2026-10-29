## Why

`query.search` 录入 `LCDEnum` 枚举查询条件时，会把普通下拉箭头误判为弹出参照触发器，导致真实页面已经打开 `.wui-select-dropdown` 后仍报 `未打开弹出参照选择框`。

该问题影响 `出库管理` 已出库页签中 `单据类型=调拨` 这类普通枚举查询条件，DSL 本身不应改写为 `popup_reference.select`。

## What Changes

- 调整查询字段录入分流：普通枚举/choice/dropdown 查询条件优先使用现有下拉选择流程。
- 保持 `YDFTreeModalSelect`、`YDFTableModalSelect`、`refuri`/refer 元数据字段继续使用弹出参照流程。
- 为 `query.search` 中 `LCDEnum`/`enumType` 普通下拉补充规格和回归测试。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `query-popup-reference-selection`: 明确 `query.search` 中 `LCDEnum` 或带 `enumType` 的普通枚举查询字段必须按 choice/dropdown 处理，不得因下拉箭头进入弹出参照流程。

## Impact

- 影响 `ydf_browser/runtime.py` 中 `fill_query_field()` 的字段类型分流。
- 增加 `tests/test_runtime.py` 覆盖查询枚举下拉边界。
- 不改变 DSL schema、命令行参数或既有弹出参照目标结构。
