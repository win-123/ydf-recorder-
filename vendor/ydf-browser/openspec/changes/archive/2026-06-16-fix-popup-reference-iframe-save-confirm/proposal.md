## Why

`执行项目立项` 新增页的 `项目负责人` 弹出参照在选中人员后仍停留在前景 iframe 弹框内，弹框页脚确认按钮是 `保存`。当前运行时把该前景参照误判为已经关闭，导致 `form.fill` 以 `confirmed=false` 返回，后续 `tab.click 财务核算信息` 在参照框未关闭的状态下失败。

这个问题会让已经支持的树表参照和 `保存` 确认语义在 iframe 式参照页上失效，需要补齐弹框仍可见时的确认与关闭判断。

## What Changes

- 修正弹出参照选择后的关闭判定：当前景 iframe 或非标准弹框仍包含可见候选区和 `保存/取消` 页脚时，运行时不能把参照当作已关闭。
- 保持 `保存` 作为弹出参照默认确认动作；当参照仍可见时必须点击弹框内的 `保存`，等待弹框关闭或字段回填。
- 在步骤结果中继续报告 `selected`、`confirmed`、`confirm_label`，用于定位是否真实执行了弹框确认。
- 为 `项目负责人` 这类 `PM_SELECT_MANAGER` iframe 参照补回归，并用真实 YAML 验证至少越过 `项目负责人` 后的 `tab.click 财务核算信息`。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `popup-reference-tree-table-selection`: 补充 iframe/非标准前景参照在选中后仍可见时必须继续执行 `保存` 确认，禁止因关闭检测假阳性提前返回。

## Impact

- 主要影响 `ydf_browser/runtime.py` 的弹出参照选择、弹框关闭检测和确认点击路径。
- 影响 `form.fill` 结构化参照字段，以及复用同一弹出参照运行时的 `popup_reference.select`。
- 需要新增或调整 `tests/test_runtime.py` 中弹框关闭判断和 `保存` 确认相关回归。
- 不改变 DSL 语法，不引入依赖，不改变普通下拉、普通树形下拉和已确认能自动关闭的参照行为。
