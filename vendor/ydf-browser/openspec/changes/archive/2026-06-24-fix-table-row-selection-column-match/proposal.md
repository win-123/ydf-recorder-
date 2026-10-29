## Why

`/Users/ken/temp/ydf-browser-问题反馈/功能-单位资金代管-预算支付全景-新增-普通转账-001.yaml` 在 `table_row_selection.select` 中按 `政府采购标识 = 是` 选择可用指标行时失败，但真实页面存在该文本值。当前运行时把单个匹配值退化为整行文本包含查找，且在多表格、iframe 页面中可能没有限定到目标表格，导致行存在时仍报未找到选择框。

## What Changes

- 修正 `table_row_selection.select target.match.column + equals` 的语义：必须按指定列读取并匹配数据行，而不是只做整行文本包含。
- 在多表格页面中优先根据目标列所属表格或显式 `target.table` 限定表格作用域，避免跨表格裸扫。
- 保持行选择语义不变：匹配列值只是定位业务行，真正选择仍点击该行选择列 checkbox 或等效行选择控件。
- 改进失败诊断，区分找不到目标列、找不到匹配行、找到行但找不到行选择控件。

## Capabilities

### New Capabilities

### Modified Capabilities
- `table-row-selection`: 修改按列匹配行选择的运行时要求，覆盖文本布尔列值和多表格作用域。

## Impact

- 影响 `ydf_browser/executor.py` 中表格作用域解析与调用参数传递。
- 影响 `ydf_browser/runtime.py` 中表格行定位、列值读取、行选择控件点击和错误诊断。
- 需要补充 executor/runtime 单测，并用单位资金代管预算支付全景真实 YAML 做回归验证。
