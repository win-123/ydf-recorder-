## Why

`实物管理-易耗品物资-入库填报-草稿页签删除-0002.yaml` 在 `editable_table.fill_row` 中给 `物资分类` 使用了 `{tree, first_available}` 结构化参照目标，但运行时把该对象字符串化写进了可编辑表格单元格，导致“选择物资类别”弹窗残留，后续 `存放仓库` 或 `入库数量` 录入连锁失败。

这类失败会把真实根因隐藏成后续列激活失败，且可能污染业务数据；可编辑表格单元格只要收到结构化弹出参照目标，就必须走参照选择流程或给出明确错误，不能降级成普通文本录入。

## What Changes

- 扩展 `editable_table.fill_row` 的结构化参照分流：字段值包含 `tree`、`tab`、`match`、`row_number`、`first_available`、`selections` 等参照语义时，必须优先进入弹出参照流程。
- 支持模板元数据为普通 `YDFInput`、但运行时会弹出参照的可编辑表格列，例如 `物资分类` 这类激活后出现树表参照的列。
- 若结构化参照目标无法打开弹窗或无法完成回填，当前字段必须失败并保留目标列、结构化目标和可见弹窗诊断，不能把对象字符串写入单元格。
- 保持普通文本、数字、普通下拉和已支持的 `YDFTreeModalSelect` / `YDFTableModalSelect` 可编辑表格列行为兼容。
- 补充回归测试和真实用例验证，覆盖 `物资分类: {tree: ..., first_available: true}` 不再被字符串化写入单元格。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `editable-table-cell-entry`: 可编辑表格录入需要识别结构化弹出参照目标，避免将对象值作为普通文本写入单元格，并在参照选择成功时透传诊断。

## Impact

- 影响 `ydf_browser/runtime.py` 中可编辑表格单元格录入分流、弹出参照打开、回填等待和失败诊断。
- 可能影响 `ydf_browser/dsl.py` 或相关规范校验，确保结构化参照目标保留为对象进入运行时。
- 需要新增或调整 `tests/test_runtime.py`、`tests/test_executor.py` 中的可编辑表格结构化参照回归。
- 需要用 `/Users/ken/temp/ydf-browser-问题反馈/实物管理-易耗品物资-入库填报-草稿页签删除-0002.yaml` 或精简探针做真实页面验证。
