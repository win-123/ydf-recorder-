## 1. 测试先行

- [x] 1.1 在 `tests/test_dsl.py` 增加 `table_row_action.click` 接受 `target.table` / `target.table_name` 且仍要求行定位字段的校验用例。
- [x] 1.2 在 `tests/test_executor.py` 增加 executor 将 `target.table=物资信息` 解析为 `table_fieldid=wzxx_table` 并传给 runtime 行聚焦的用例。
- [x] 1.3 在 `tests/test_runtime.py` 增加 runtime 按 `table_fieldid` 限定 `focus_table_row_by_index` / `focus_table_row` 行搜索范围的用例。
- [x] 1.4 在 `tests/test_executor.py` 增加紧邻 `editable_table.fill_row` 后未写 `target.table` 的 `table_row_action.click` 复用前序表格作用域的用例。

## 2. 最小实现

- [x] 2.1 更新 DSL schema，让 `table_row_action.click target` 接受 `table` 和 `table_name`，但不把它们视为行定位属性。
- [x] 2.2 更新 executor 的 `_execute_table_row_action_click`，解析显式表格作用域并把 `table`、`table_fieldid`、`table_columns` 传给 runtime。
- [x] 2.3 更新 runtime 行聚焦方法，复用 `_table_selection_context` 在指定表格 root 内按 `row_number` 或 `match` hover 业务行。
- [x] 2.4 保持 `click_row_action` 的现有可见行级按钮点击流程，不新增按钮 selector 框架。
- [x] 2.5 在步骤结果和失败诊断中保留 `table`、可用时的 `table_fieldid` 和行定位信息。
- [x] 2.6 记录最近一次成功的可编辑表格作用域，并在紧邻的未显式指定表格行按钮点击中消费该作用域。

## 3. 验证

- [x] 3.1 运行新增的 focused pytest 用例，确认失败先被测试覆盖再由实现修复。
- [x] 3.2 运行真实 YAML：`./.venv/bin/python -m ydf_browser.cli run --dsl '/Users/ken/temp/ydf-browser-问题反馈/实物管理-易耗品物资-领用分配-未分配页签分配-0001 (1).yaml' --headless --report-file /tmp/ydf-material-allocation-row-action-after.json`。已验证第 6 步 `table_row_action.click` 复用前序 `物资信息 / wzxx_table` 作用域并点击成功；原始用例随后停在第 8 步 `target.table=物资申请出库信息` 与页面实际可编辑表格标题 `表格` 不匹配。
- [x] 3.3 运行完整回归：`./.venv/bin/python -m pytest`。
- [x] 3.4 运行 OpenSpec 门禁：`openspec validate support-scoped-table-row-actions --strict` 和 `./scripts/check_openspec_language.py --change support-scoped-table-row-actions`。
