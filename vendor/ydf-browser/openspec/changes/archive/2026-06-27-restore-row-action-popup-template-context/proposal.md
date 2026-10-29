## Why

真实用例在 `table_row_action.click 选择库存` 打开动态参照模板并完成 `popup_reference.select` 后，executor 没有恢复上一层分配页模板，导致后续 `editable_table.fill_row` 误用已关闭参照模板中的通用表格标签 `表格`，错误提示要求修改本来正确的 `target.table=物资申请出库信息`。

## What Changes

- 扩展弹出参照选择后的动态模板恢复规则，覆盖由 `table_row_action.click` 直接打开参照模板的链路。
- 仅在参照模板已关闭且上一层模板重新可见时恢复，继续保留仍处于前景的行级编辑表单。
- 在恢复步骤结果中沿用 `restored_template` 和 `auto_restored_template: true`，便于报告确认恢复行为。
- 增加回归测试，并使用原始真实 YAML 验证后续可编辑表格按 `物资申请出库信息` 继续执行。
- 不改变 DSL 语法，也不要求用户删除或修改正确的 `target.table`。

## Capabilities

### New Capabilities

### Modified Capabilities

- `dynamic-template-context-restoration`: 补充由行级动作直接打开弹出参照时，参照关闭后恢复上一层活动模板的要求。

## Impact

- 影响 `ydf_browser/executor.py` 中 `popup_reference.select` 后的动态模板恢复判定。
- 影响 `tests/test_executor.py` 中动态模板上下文回归测试。
- 不引入新依赖，不改变弹出参照过滤、选择、确认或可编辑表格 DSL 语义。
