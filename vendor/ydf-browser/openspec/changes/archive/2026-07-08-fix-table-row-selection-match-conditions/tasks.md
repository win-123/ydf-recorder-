## 1. 回归测试

- [x] 1.1 在 `tests/test_runtime.py` 增加聚焦回归：第一条行只满足首条件、第四条行满足全部 `target.match.conditions` 时，runtime 点击第四条行选择控件。
- [x] 1.2 覆盖条件顺序不同但目标行相同的场景，防止实现继续依赖第一个条件决定最终行。

## 2. Runtime 修复

- [x] 2.1 调整 `PlaywrightRuntime.select_table_row()` 到 `_find_visible_table_data_row_by_values()` 的参数链路，保留完整 `match.conditions`。
- [x] 2.2 让 `_TABLE_ROW_VALUES_SCRIPT` 调用收到完整条件和全部声明列，继续复用现有列身份匹配、表格作用域和 WUI header/body 聚合逻辑。
- [x] 2.3 保持单条件 `target.match.column` / `target.match.equals`、无 checkbox 行点击兜底和树形表格展开行为兼容。

## 3. 验证

- [x] 3.1 运行聚焦测试：`./.venv/bin/python -m pytest tests/test_runtime.py -k "table_row_selection or composite" -q`。
- [x] 3.2 运行真实 DSL：`./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/流程-预算管理-调整调剂_财政-待分配预算管理（预算部门）逆向-001.yaml --headless --report-file <tmp-report.json>`。
- [x] 3.3 确认真实报告中 `table_row_selection.select` 仍限定在 `table1` / `table1_drag`，且页面实际选中满足 `一级项目名称=财政一级项目ys06231632` 与 `指标金额=888.00` 的业务行。
- [x] 3.4 运行 OpenSpec 门禁：`openspec validate fix-table-row-selection-match-conditions --strict` 和 `./scripts/check_openspec_language.py --change fix-table-row-selection-match-conditions`。
- [x] 3.5 按共享 runtime 改动风险决定是否运行完整 `./.venv/bin/python -m pytest -q`；若未运行，在交付说明中明确原因。
