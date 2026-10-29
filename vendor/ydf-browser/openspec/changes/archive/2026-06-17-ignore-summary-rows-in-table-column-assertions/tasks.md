## 1. 回归用例

- [x] 1.1 为 `_TABLE_COLUMN_VALUES_SCRIPT` 增加单元测试，覆盖 WUI `tfoot-tr/bsubtotal` 小计行不进入 `table.assert_column_values` 返回值。
- [x] 1.2 增加中文汇总文本测试，覆盖首单元格或整行以 `小计/合计/汇总/总计` 开头的行被过滤。
- [x] 1.3 确认普通业务行中目标列值仍按现有 identity/索引/几何路径被采集。

## 2. 实现

- [x] 2.1 在 `ydf_browser/runtime.py` 的 `_TABLE_COLUMN_VALUES_SCRIPT` 中新增汇总行识别逻辑。
- [x] 2.2 在 `dataRowsForTable()` 或等价的列值采集行枚举路径中过滤汇总行。
- [x] 2.3 确认过滤不影响 `table.assert_columns`、`table.assert_row_values` 和可编辑表格已有行为。

## 3. 验证

- [x] 3.1 运行新增/相关目标测试，确认失败先复现、实现后通过。
- [x] 3.2 运行真实用例 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-项目库-YDF-82797-0001-执行项目新增父子项目和设置经费管理员.yaml`，确认 `项目名称` 列断言不再采集 `190,000.00`。
- [x] 3.3 运行 `openspec validate ignore-summary-rows-in-table-column-assertions --strict`。
- [x] 3.4 运行完整 `./.venv/bin/python -m pytest`，确认全量回归通过。
