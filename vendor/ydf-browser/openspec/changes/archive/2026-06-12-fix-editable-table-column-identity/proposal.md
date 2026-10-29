## Why

`editable_table.fill_row` 当前会把可编辑表格列候选解析到模板字段，但运行时定位单元格时只使用列名、行号和表格名称。真实用例 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-预算编制-YDF-80457-0002.yaml` 中，`项目测算信息.计量数` 的值 `500` 被写入同表的 `备注` 单元格，步骤仍被报告为成功，最终保存提示测算金额为 `0.00`。

## What Changes

- `editable_table.fill_row` 的运行时单元格定位需要使用模板列身份，包括列 `fieldid`、`dataField`、表格 `fieldid` 和列组件类型，而不是仅依赖可见表头文本和几何位置。
- 单元格定位应优先匹配目标列身份；只有页面 DOM 缺少可用身份属性时，才允许继续使用现有表头文本和几何映射兜底。
- 录入成功结果应能证明写入的是目标列，至少在调试/报告数据中记录目标列身份和实际定位来源，避免错列写入被标记为成功。
- 增加回归覆盖：`计量数(estVal)` 与同一表内 `备注(activityDesc)` 共存时，`计量数: "500"` 不得写入备注列。

## Capabilities

### New Capabilities
- `editable-table-cell-entry`: 约束 `editable_table.fill_row` 在可编辑表格中按模板列身份定位并录入目标单元格，覆盖横向滚动、同表 formItem/column 共存、错列诊断和回归验证。

### Modified Capabilities
- 无。

## Impact

- 影响 `ydf_browser/executor.py` 中可编辑表格列候选传递逻辑。
- 影响 `ydf_browser/runtime.py` 中 `_activate_editable_table_cell`、`_EDITABLE_TABLE_CELL_SELECTOR_SCRIPT` 和录入结果/诊断数据。
- 影响 `tests/test_runtime.py`、`tests/test_executor.py` 中可编辑表格单元格定位和报告行为的回归测试。
- 不改变 DSL 语法；现有 `editable_table.fill_row` 用例应保持兼容。
