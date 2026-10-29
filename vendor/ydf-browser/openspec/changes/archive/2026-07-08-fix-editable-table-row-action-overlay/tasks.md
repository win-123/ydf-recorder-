## 1. 测试先行

- [x] 1.1 在 `tests/test_runtime.py` 增加单测，构造目标行行级动作浮层覆盖目标单元格的场景，验证运行时会点击同一行最右侧收起按钮后重新激活目标 cell。
- [x] 1.2 在 `tests/test_runtime.py` 增加单测，验证字段回填确认后会尝试恢复当前表格当前行的默认行按钮显示行为。
- [x] 1.3 在 `tests/test_runtime.py` 增加单测，验证恢复失败时保留已确认回填的字段结果并记录恢复诊断。
- [x] 1.4 在 `tests/test_runtime.py` 增加单测，验证收起和恢复查找限定在当前目标表格和目标行，不影响其他表格行按钮。
- [x] 1.5 增加回归测试，验证非空可编辑表格点击新增后真实数据行数量未增长时，`editable_table.add_row` 不得报告成功。

## 2. 实现

- [x] 2.1 扩展可编辑表格单元格激活流程，在目标 cell 激活失败或检测到行级动作遮挡时，查找当前目标行最右侧收起入口。
- [x] 2.2 点击收起入口后重新执行 `_find_editable_table_cell_selector()`，并基于新的目标 cell locator 执行既有激活和录入逻辑。
- [x] 2.3 在字段录入并确认回填后，尝试恢复当前表格当前行的默认行按钮显示行为；恢复失败只记录诊断，不覆盖已成功回填结果。
- [x] 2.4 将收起、重新定位、恢复结果写入可编辑表格激活或字段诊断，便于报告区分真实不可编辑列和行按钮遮挡。
- [x] 2.5 记录 `editable_table.add_row` 点击前后目标表格行状态；当未打开行编辑表单模板且真实数据行数量未增长时，报告新增行未生效。

## 3. 验证

- [x] 3.1 运行聚焦测试：`./.venv/bin/python -m pytest tests/test_runtime.py -q`。
- [x] 3.2 运行 OpenSpec 校验：`openspec validate fix-editable-table-row-action-overlay --strict` 和 `./scripts/check_openspec_language.py --change fix-editable-table-row-action-overlay`。
- [x] 3.3 使用真实 DSL 验证：`./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/14功能-预算执行-采购管理-采购需求编制-新增提交-0001.yaml --headless --report-file <report.json>`。
- [x] 3.4 检查真实验证报告，确认 `editable_table.fill_row` 已成功录入 `需求清单.备注=UI`，且没有因行级动作遮挡报告 `可编辑表格单元格激活后未出现可输入控件`。
- [x] 3.5 根据改动风险运行相邻回归；若只改 `ydf_browser/runtime.py` 的可编辑表格激活共享入口，准备交付前运行完整 `./.venv/bin/python -m pytest`。
- [x] 3.6 使用追加真实 DSL 验证第二次 `editable_table.add_row` 形成 2 条真实数据行并维护第 2 行；未新增真实数据行的失败路径由聚焦单测覆盖。
