## 1. 回归测试

- [x] 1.1 在 `tests/test_runtime.py` 增加聚焦回归：同一 `table_fieldid` 存在背景旧候选根和前景候选根时，背景旧根有 `selectableRows` 但无可接收业务行，前景根无 checkbox 但有可接收业务行，runtime 必须选择前景根并点击业务行。
- [x] 1.2 覆盖 fieldid 已解析但候选根均无可接收业务行时必须失败，且不得按 `target.table` 文本回退到其它表格根。
- [x] 1.3 保留或补充 WUI 表头/表体分裂聚合覆盖，确认新增前景业务行优先级不破坏现有 fieldid cluster 选择。

## 2. Runtime 修复

- [x] 2.1 调整 `_TABLE_FIELDID_ROOT_SELECTOR_SCRIPT` 的候选指标，增加基于有效业务行和 `elementFromPoint` 的可接收 pointer 事件信号。
- [x] 2.2 调整同 fieldid 候选排序，让前景可接收业务行根优先于仅有 `selectableRows` 的背景旧根，并保留 `selectableRows` 作为同等级候选内的辅助排序。
- [x] 2.3 确认 `table_fieldid` 成功解析后仍只在 fieldid 候选内决策，不新增按 `target.table` 文本全局回退路径。
- [x] 2.4 保持按行号选择的 checkbox 优先、无 checkbox 行点击兜底、失败诊断和实际根 `selection_debug` 兼容。

## 3. 真实用例验证

- [x] 3.1 运行聚焦测试：`./.venv/bin/python -m pytest tests/test_runtime.py -k "table_fieldid or table_row_selection or row_selection" -q`。
- [x] 3.2 运行真实 DSL：`./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/流程-预算管理-调整调剂_财政-待分配预算管理（预算部门）逆向-001.yaml --headless --report-file <tmp-report.json>`。
- [x] 3.3 检查真实报告中第 6 步 `table_row_selection.select` 命中 `table=调出方` / `table_fieldid=table1`，并且 `selection_debug` 显示实际点击的是前景业务行根而非背景旧根。

## 4. 交付门禁

- [x] 4.1 运行 OpenSpec 校验：`openspec validate fix-table-fieldid-root-foreground-selection --strict`。
- [x] 4.2 运行 OpenSpec 语言检查：`./scripts/check_openspec_language.py --change fix-table-fieldid-root-foreground-selection`。
- [x] 4.3 按共享 runtime 改动风险运行相关聚焦测试；准备交付前运行完整 `./.venv/bin/python -m pytest -q`，若未运行必须在交付说明中明确原因。
