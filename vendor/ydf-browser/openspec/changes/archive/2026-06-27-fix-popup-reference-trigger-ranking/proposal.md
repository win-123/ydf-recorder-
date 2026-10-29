## Why

`功能-单位资金代管-预算支付全景-新增-普通转账-001` 在本机网络恢复后可以稳定通过，但两台 Windows 电脑使用 0.1.7 均在 `单位内设机构` 弹出参照字段稳定失败。诊断专版报告显示运行时点击了同一字段根内的 `show-search` 输入容器，没有点击右侧真实 `modal-btn` 参照按钮，导致没有发起网络请求、也没有打开参照弹窗。

这个问题不是 DSL 或业务数据问题，而是弹出参照触发候选排序过度依赖右边界和面积；Windows 渲染下搜索容器与按钮右边界非常接近，搜索容器可能排在真实按钮之前。

## What Changes

- 修正弹出参照打开阶段的触发候选排序：真实按钮、`modal-btn`、`wui-button`、`icon-only`、`*_btn` 这类参照按钮必须优先于 `show-search`、`combobox`、输入框等搜索容器。
- 保留右边界和面积排序作为同分兜底，兼容已有没有明确按钮标识的参照控件。
- 保留诊断专版中新增的弹出参照打开诊断，并在候选诊断中输出排序权重，便于后续判断是否仍点错元素。
- 增加回归测试，防止弹出参照打开逻辑退回到仅按几何位置排序。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `popup-reference-tree-table-selection`: 补充弹出参照字段打开时的触发控件选择要求，确保参照按钮优先于字段内搜索输入容器，并要求失败诊断保留候选排序依据。

## Impact

- 影响 `ydf_browser/runtime.py` 的 `_open_popup_reference_dialog()` 触发候选排序和诊断采集。
- 影响 `form.fill`、`query.search`、`editable_table.fill_row` 等复用弹出参照打开流程的字段录入路径。
- 不引入 DSL 语法变化，不改变弹出参照候选选择、过滤、匹配和确认语义。
- 不新增依赖；诊断行为仍由 `YDF_BROWSER_POPUP_DIAG` 环境变量控制。
