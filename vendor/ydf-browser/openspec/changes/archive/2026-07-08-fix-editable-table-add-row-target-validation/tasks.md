## 1. 回归复现

- [x] 1.1 在 `tests/test_runtime.py` 增加最小回归，构造目标 `需求清单` 空表和相邻已有数据表，验证 `editable_table.add_row` 不会把相邻表格已有行当作目标新增成功。
- [x] 1.2 覆盖成功路径：点击新增后目标表格 root 内出现真实可编辑数据行时，步骤结果的 `row_state` 只来自目标表格。

## 2. Runtime 实现

- [x] 2.1 调整 `ydf_browser/runtime.py` 中 `_EDITABLE_TABLE_ADD_ROW_SCRIPT` 的目标 root 解析，让点击后验证优先使用 `tableFieldid`、目标列身份或等价目标表格 root。
- [x] 2.2 移除或收窄 `validationRootFor` 向外层容器寻找更多行的成功判定，避免外层容器和相邻表格污染目标 `row_state`。
- [x] 2.3 当点击后目标表格仍为空态、只有表头或没有可供 `editable_table.fill_row` 使用的数据行时，让 `add_row` 当前步骤失败，并输出 `target.table`、`table_fieldid`、候选 root 摘要和截图诊断。

## 3. 验证

- [x] 3.1 运行聚焦单测：`./.venv/bin/python -m pytest tests/test_runtime.py -k "editable_table_add_row"`.
- [x] 3.2 真实执行问题 YAML：`./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/14功能-预算执行-采购管理-采购需求编制-新增提交-0001.yaml --headless --report-file /tmp/ydf-proc-demand-add-row-after-fix.json`.
- [x] 3.3 检查真实报告，确认 `editable_table.add_row` 的成功或失败与 `需求清单` 目标表格真实行状态一致；若后续 `fill_row` 或保存失败，单独分类为参照、数据或业务校验问题。
- [x] 3.4 运行完整测试：`./.venv/bin/python -m pytest`.
- [x] 3.5 运行 OpenSpec 门禁：`openspec validate fix-editable-table-add-row-target-validation --strict` 和 `./scripts/check_openspec_language.py --change fix-editable-table-add-row-target-validation`。
