## 1. 回归测试先行

- [x] 1.1 在 `tests/test_dsl.py` 增加校验，覆盖 `table.assert_column_values` 和 `table.assert_row_values` 接受可选 `target.table` / `target.table_name`。
- [x] 1.2 在 `tests/test_executor.py` 增加 `table.assert_column_values` 解析目标表格并向 runtime 传递 `table_fieldid`、`table_columns` 的测试。
- [x] 1.3 在 `tests/test_executor.py` 增加 `table.assert_row_values` 使用 match 列和 fields 列推断唯一目标表格的测试。
- [x] 1.4 在 `tests/test_executor.py` 增加多表格无法唯一推断时拒绝数据值断言的测试。
- [x] 1.5 在 `tests/test_runtime.py` 增加 runtime 单元测试，覆盖 `可授权金额` 与 `起始时间`、`项目名称` 相邻时不串列。
- [x] 1.6 在 `tests/test_runtime.py` 增加 header/body 分离或固定列副本场景，验证行值断言按列 identity 读取目标单元格。

## 2. DSL 与 Executor 实现

- [x] 2.1 扩展 `ydf_browser/dsl.py`，允许 `table.assert_column_values` 和 `table.assert_row_values` 的 target 包含 `table` / `table_name`。
- [x] 2.2 在 `ydf_browser/executor.py` 中抽取或复用表格作用域解析 helper，供 `assert_columns`、`assert_column_values`、`assert_row_values` 共享。
- [x] 2.3 修改 `_execute_table_assert_column_values()`，解析目标表格、模板列清单和可用 headers 后再调用 runtime。
- [x] 2.4 修改 `_execute_table_assert_row_values()`，将 match 列和 fields 列纳入表格推断，并把表格上下文传给 runtime。
- [x] 2.5 改进数据值断言失败信息，包含目标列、匹配条件、table/table_fieldid、headers 和缺失/歧义原因。

## 3. Runtime 实现

- [x] 3.1 扩展 `PlaywrightRuntime.collect_table_column_values()` 支持可选 `table`、`table_fieldid`、`table_columns` 参数，并保持旧调用兼容。
- [x] 3.2 扩展 `PlaywrightRuntime.collect_table_row_values()` 支持可选 `table`、`table_fieldid`、`table_columns` 参数，并保持旧调用兼容。
- [x] 3.3 让列值和行值采集复用 `_table_selection_context()`，只在目标表格作用域内查 header/body/cell。
- [x] 3.4 更新 `_TABLE_COLUMN_VALUES_SCRIPT`，按目标表格内真实表头和列 identity 读取列值，避免全页面裸扫和相邻列串读。
- [x] 3.5 更新 `_TABLE_ROW_VALUES_SCRIPT`，按 match 条件列定位业务行，再按同一行的目标字段列读取值。
- [x] 3.6 保留必要的横向滚动读取能力，确保视口外目标列可被采集。

## 4. 用例修正

- [x] 4.1 修改 `/Users/ken/temp/ydf-browser-问题反馈/特性-项目管理-项目预算-YDF-80492-YDFJF-1950-0001 (1).yaml`，保留授权、选职员授权、保存流程。
- [x] 4.2 将最后一步从 `table.assert_column_values column=可授权金额 equals=400.00` 改为 `table.assert_row_values`。
- [x] 4.3 最后一步使用 `target.match.column=被授权人名称`、`target.match.equals=人员二十二` 定位行，并在 `target.fields` 中断言 `可授权金额: "400.00"`。
- [x] 4.4 如实现后真实页面仍存在多表格歧义，在用例最后一步补充 `target.table` 或更稳定的多条件 match，而不是退回整列断言。

## 5. 验证

- [x] 5.1 运行聚焦单测：`./.venv/bin/python -m pytest tests/test_dsl.py tests/test_executor.py tests/test_runtime.py -k "assert_column_values or assert_row_values or table_columns"`。
- [x] 5.2 运行目标 YAML 语法校验：`./.venv/bin/python -m ydf_browser.cli validate --dsl "/Users/ken/temp/ydf-browser-问题反馈/特性-项目管理-项目预算-YDF-80492-YDFJF-1950-0001 (1).yaml"`。
- [x] 5.3 使用源码入口真实执行目标 YAML：`./.venv/bin/python -m ydf_browser.cli run --dsl "/Users/ken/temp/ydf-browser-问题反馈/特性-项目管理-项目预算-YDF-80492-YDFJF-1950-0001 (1).yaml" --headless --report-file /tmp/ydf-ydf80492-row-value-fixed-report.json`。
- [x] 5.4 确认真实报告中最后一步 `table.assert_row_values` 成功，并记录 `被授权人名称=人员二十二` 行的 `可授权金额=400.00`。
- [x] 5.5 回归运行现有表格断言相关测试，确认 `table.assert_columns` 行为未被破坏。

## 6. OpenSpec 验收

- [x] 6.1 运行 `openspec validate fix-table-value-assertion-column-mapping --strict`。
- [x] 6.2 运行 `openspec status --change "fix-table-value-assertion-column-mapping"`，确认 tasks 可用于 apply。
