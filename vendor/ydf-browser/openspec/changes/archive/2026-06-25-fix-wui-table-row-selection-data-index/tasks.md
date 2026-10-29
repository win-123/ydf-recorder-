## 1. 复现与定位

- [x] 1.1 记录原始 YAML 的失败报告路径，确认 `table_row_selection.select` 已进入 `kyzb_table` 但列值匹配失败。报告：`/tmp/ydf-central-payment-normal-transfer-report.json`
- [x] 1.2 用 `target.table=可用指标 + row_number=1` 临时验证同一表格行 checkbox 可选，排除选择控件问题。报告：`/tmp/ydf-central-payment-normal-transfer-row1-table-report.json`

## 2. 测试

- [x] 2.1 增加 runtime 回归测试，覆盖 WUI 表头 `fieldid=kyzb_table_isGovPurName` 与行单元格 `data-index=isGovPurName` 的列值匹配。
- [x] 2.2 确认已有按列值选择测试仍覆盖“不退化为整行文本误选”。

## 3. 实现

- [x] 3.1 调整 `_TABLE_ROW_VALUES_SCRIPT` 的 identity 匹配，支持表头 `fieldid` 与行单元格 `data-index` / `data-field` 的后缀式模板列对齐。
- [x] 3.2 保持现有完全 identity 匹配、索引兜底和 checkbox 点击逻辑不变。

## 4. 验证

- [x] 4.1 运行新增及相关 runtime 测试。`./.venv/bin/python -m pytest tests/test_runtime.py::test_table_row_values_script_matches_wui_header_fieldid_to_cell_data_index tests/test_runtime.py::test_playwright_runtime_single_column_match_uses_column_row_lookup tests/test_runtime.py::test_playwright_runtime_reports_column_match_row_without_selection_control tests/test_runtime.py::test_playwright_runtime_collect_table_column_values_scopes_to_table_fieldid tests/test_runtime.py::test_playwright_runtime_collect_table_row_values_passes_table_identity_payload`
- [x] 4.2 运行 `openspec validate fix-wui-table-row-selection-data-index --strict`。
- [x] 4.3 运行 `./scripts/check_openspec_language.py --change fix-wui-table-row-selection-data-index`。
- [x] 4.4 重新运行原始 YAML，确认 `table_row_selection.select` 越过第 3 步并记录报告路径。报告：`/tmp/ydf-central-payment-normal-transfer-after-data-index-report.json`；第 3 步 `table_row_selection.select` 成功，后续第 5 步因 `收款人全称=自动化测试` 当前参照无数据失败。
