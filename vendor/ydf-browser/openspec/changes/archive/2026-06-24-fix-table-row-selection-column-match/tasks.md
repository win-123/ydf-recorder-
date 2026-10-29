## 1. Reproduce

- [x] 1.1 用 `/Users/ken/temp/ydf-browser-问题反馈/功能-单位资金代管-预算支付全景-新增-普通转账-001.yaml` 复现 `政府采购标识=是` 行存在但 `table_row_selection.select` 失败的问题，并记录报告路径。报告：`/tmp/ydf-unit-fund-normal-transfer-report.json`
- [x] 1.2 抽取失败报告中的关键证据：菜单 `预算支付全景-单位资金`、表格 `可用指标/kyzb_table`、目标列 `政府采购标识`、当前错误中的行统计。

## 2. Tests

- [x] 2.1 增加 executor 单测：未写 `target.table` 且 `match.column` 唯一属于一张主表时，自动解析并传递 `table_fieldid/table_columns`。
- [x] 2.2 增加 executor 单测：多张主表都包含目标列且未写 `target.table` 时失败并提示补充 `target.table`。
- [x] 2.3 增加 runtime 单测：单条件 `match.column=政府采购标识, equals=是` 必须按该列值选择目标行，不能因整行文本包含 `是` 误选其它行。
- [x] 2.4 增加 runtime 单测：找到目标业务行但没有行选择控件时，错误信息包含表格、列和值。

## 3. Implementation

- [x] 3.1 在 `WorkflowExecutor._execute_table_row_selection_select` 附近复用现有表格列归属解析，支持按 `target.match.column` 推断唯一目标表格。
- [x] 3.2 调整 runtime 行匹配分支，使存在 `column` 的单值匹配走列值读取路径。
- [x] 3.3 保留无 `column` 的旧整行文本匹配行为。
- [x] 3.4 改进失败诊断，区分目标列缺失、匹配行缺失和行选择控件缺失。

## 4. Verify

- [x] 4.1 运行新增/相关单测。
- [x] 4.2 运行完整 `./.venv/bin/python -m pytest`。
- [x] 4.3 重新运行单位资金代管普通转账 YAML，确认 `table_row_selection.select` 能越过第 3 步。报告：`/tmp/ydf-unit-fund-normal-transfer-final-report.json`
- [x] 4.4 运行 `openspec validate fix-table-row-selection-column-match --strict`。
- [x] 4.5 运行 `./scripts/check_openspec_language.py --change fix-table-row-selection-column-match`。
