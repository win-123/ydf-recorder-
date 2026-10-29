## Why

真实用例 `14功能-预算执行-采购管理-采购需求编制-新增提交-0001.yaml` 在第一轮 `editable_table.add_row` 和 `editable_table.fill_row` 成功后，第二次对同一 `需求清单` 执行 `editable_table.add_row` 时点击后行数没有增长，失败为 `before_rows=1; after_rows=1`。现有失败判定是正确的，但运行时在连续填行后再次新增前缺少对可编辑单元格编辑态和行级悬浮按钮的稳定收口，导致页面可能吞掉首次新增点击。

## What Changes

- 在 `editable_table.add_row` 运行时点击目标表格新增入口前，先收口当前可编辑表格的激活编辑态、选择下拉和行级悬浮/更多按钮状态。
- 当目标表格解析出 `table_fieldid` 时，运行时优先使用 `${table_fieldid}_add_button` 对应的可见 fieldid 入口作为新增按钮。
- 当目标表格已有真实数据行且第一次点击后行数未增长、也未打开行编辑表单模板时，在同一目标表格作用域内做一次受控重试。
- 保留现有成功门禁：只有目标表格真实数据行数量增长，或明确打开行编辑表单模板，才报告 `editable_table.add_row` 成功。
- 保留现有失败门禁：重试后仍未增长时继续失败，并输出点击前后行数、目标表格身份和候选诊断。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `editable-table-cell-entry`: 补充 `editable_table.add_row` 在连续 `fill_row -> add_row` 链路中的表格 fieldid 新增入口优先定位、编辑态/悬浮层收口和受控重试语义。

## Impact

- 影响 `ydf_browser/runtime.py` 中 `add_editable_table_row` 的点击前收口、点击后验证和重试逻辑。
- 可能补充 `tests/test_runtime.py` 或相邻 runtime 聚焦测试，覆盖已有数据行、首次点击未增长、收口后重试增长的路径。
- 需要用真实 DSL `/Users/ken/temp/ydf-browser-问题反馈/14功能-预算执行-采购管理-采购需求编制-新增提交-0001.yaml` 验证第二次新增和后续填行成功。
- 不改变 DSL schema、用户可见字段或 `editable_table.add_row` 的既有成功判定。
