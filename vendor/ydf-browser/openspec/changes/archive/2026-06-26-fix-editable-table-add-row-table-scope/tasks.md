## 1. 回归测试

- [x] 1.1 在 `tests/test_executor.py` 增加用例，覆盖 `editable_table.add_row target.table` 写页面分组标题时可解析到唯一模板可编辑表格。
- [x] 1.2 在 `tests/test_runtime.py` 增加用例，覆盖目标表格名不可见但传入表格身份时仍能在目标 root 内点击 `新增`。
- [x] 1.3 在 `tests/test_runtime.py` 增加用例，覆盖点击 `新增` 后目标表格仍为 `暂无数据` 时 `editable_table.add_row` 失败并输出诊断。

## 2. 实现修复

- [x] 2.1 调整 `ydf_browser/executor.py`，让 `editable_table.add_row` 将 `target.table` 解析为目标可编辑表格身份，并把规范化表格名、表格 fieldid 或等价候选传给 runtime。
- [x] 2.2 调整 `ydf_browser/runtime.py` 的可编辑表格新增行定位逻辑，优先使用 executor 传入的目标表格身份限定新增入口，页面可见标题仅作为兜底。
- [x] 2.3 调整 `add_editable_table_row` 的成功判定，点击后等待目标表格出现真实可编辑数据行；仍为空态或无行时当前步骤失败。
- [x] 2.4 保持未指定 `target.table` 的既有单表点击语义，并保留现有诊断字段。

## 3. 验证

- [x] 3.1 运行新增和相关既有测试：`./.venv/bin/python -m pytest tests/test_executor.py tests/test_runtime.py`。
- [x] 3.2 使用问题 YAML 的当前版本真实执行，确认 `editable_table.add_row` 能越过 `缴款明细信息`/`缴库明细表格` 不一致问题，并在报告中保留目标表格诊断。
- [x] 3.3 运行完整测试：`./.venv/bin/python -m pytest`。
- [x] 3.4 运行 OpenSpec 门禁：`openspec validate fix-editable-table-add-row-table-scope --strict` 和 `./scripts/check_openspec_language.py --change fix-editable-table-add-row-table-scope`。
