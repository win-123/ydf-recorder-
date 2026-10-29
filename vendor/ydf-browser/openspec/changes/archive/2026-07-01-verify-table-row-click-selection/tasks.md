## 1. 回归测试

- [x] 1.1 为 `_try_click_table_row_for_selection()` 增加无 checkbox 行点击后必须验证选中态的 runtime 单元测试。
- [x] 1.2 为 `select_table_row_by_index()` 增加 `target.table + row_number` 无 checkbox 行点击成功和未选中失败的回归测试。
- [x] 1.3 为按列匹配无 checkbox 行点击路径增加共享选中态验证回归，避免只修行号路径。
- [x] 1.4 为 executor 步骤报告增加行点击诊断字段的回归测试。

## 2. Runtime / Executor 实现

- [x] 2.1 在 runtime 中实现共享的行点击选中态验证 helper，识别目标行或等效当前行的真实 selected/current/active 证据。
- [x] 2.2 修改无 checkbox row-click fallback，使 `row.click()` 后无选中证据时返回失败而不是成功。
- [x] 2.3 将 `target.row_number`、`target.first_available`、`target.match` / `target.rows` 的 row-click fallback 统一接入该验证。
- [x] 2.4 在 runtime/executor 中带出最小可审计选择诊断，包括 `strategy`、`selected_after`、`table`、`table_fieldid` 和目标行信息。

## 3. 真实验证

- [x] 3.1 使用 `/Users/ken/temp/ydf-browser-问题反馈/流程-预算管理-调整调剂_财政-待分配预算管理（预算部门）-分配正向-002.yaml` 复现并确认第 6 步不再假成功。
- [x] 3.2 修复后重跑同一真实 YAML，确认 `调出方` 行真实选中，`调入方` 增行和首个字段弹出参照可继续执行。
- [x] 3.3 运行 `openspec validate verify-table-row-click-selection --strict` 和 `./scripts/check_openspec_language.py --change verify-table-row-click-selection`。
- [x] 3.4 运行完整测试套件 `./.venv/bin/python -m pytest`。
