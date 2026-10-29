## 1. 回归测试先行

- [x] 1.1 在 `tests/test_runtime.py` 增加失败用例，构造同一可编辑表格中 `计量数(estVal)` 与 `备注(activityDesc)` 共存的 DOM，验证 `计量数: "500"` 只命中 `estVal` 单元格。
- [x] 1.2 在 `tests/test_runtime.py` 增加横向滚动或列重排后重新定位的用例，验证每个字段录入前都会重新按目标列身份生成 selector。
- [x] 1.3 在 `tests/test_runtime.py` 增加身份属性缺失的兜底用例，验证仍可按表头文本和几何映射录入，并记录 `text-geometry` 类定位来源。
- [x] 1.4 在 `tests/test_executor.py` 增加用例，验证 executor 将列 `fieldid`、`data_field`、`region_fieldid` 等候选身份传递到 runtime，并在步骤结果中保留诊断信息。

## 2. 运行时身份定位实现

- [x] 2.1 扩展 `PlaywrightRuntime.fill_editable_table_row()` 与 `_activate_editable_table_cell()` 的调用链，让当前列候选进入单元格定位 payload。
- [x] 2.2 扩展 `_EDITABLE_TABLE_CELL_SELECTOR_SCRIPT`，在目标表格上下文中优先按 `columnFieldid`、`dataField`、`tableFieldid` 和常见 DOM 属性匹配 header/cell。
- [x] 2.3 保留现有表头文本和几何映射作为兜底，并将实际定位来源写入 debug 或返回数据。
- [x] 2.4 增加身份冲突检测：当 runtime 能判断实际命中单元格身份与目标列身份冲突时，`editable_table.fill_row` 必须失败并输出列名、目标身份、实际身份或定位来源。
- [x] 2.5 保持现有 DSL 和步骤结果兼容，只追加每个字段的 `fieldid`、`data_field`、`table_fieldid`、`locator_source` 等诊断字段，不删除原有 `column` 和 `value`。

## 3. 验证与真实用例

- [x] 3.1 运行聚焦测试：`pytest tests/test_runtime.py tests/test_executor.py -q`。
- [x] 3.2 运行 OpenSpec 校验：`openspec validate fix-editable-table-column-identity --strict`；如本地 CLI 不支持该形式，则使用仓库当前支持的等价 change 校验命令。
- [x] 3.3 使用问题用例做真实验证：`./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-预算编制-YDF-80457-0002.yaml --headless`。
- [x] 3.4 检查真实验证报告，确认 `editable_table.fill_row` 中 `计量数` 的诊断身份为 `estVal`，`备注(activityDesc)` 未被写入 `"500"`，保存不再因测算金额 `0.00` 触发原 warning。
