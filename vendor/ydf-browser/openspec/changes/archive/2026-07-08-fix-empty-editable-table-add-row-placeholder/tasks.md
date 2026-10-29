## 1. 复现与测试

- [x] 1.1 保留本次真实失败证据：`editable_table.add_row target.table=调入方` 解析到 `table_fieldid=table2`，两次点击 `.ydf-table-placeholder-add-button` 后报告 `retry_count=1`。
- [x] 1.2 为 `_EDITABLE_TABLE_ADD_ROW_SCRIPT` 增加聚焦测试，覆盖空目标表格 placeholder 点击后出现第一条真实数据行时成功且不触发重试。
- [x] 1.3 增加聚焦测试，覆盖 placeholder 按钮自身、外层容器或相邻表格行数不能作为目标表格 `row_state`。
- [x] 1.4 保留既有非空表格未增长受控重试测试，确认可靠目标 root 已有真实行时仍最多重试一次。

## 2. Runtime 实现

- [x] 2.1 调整 `_EDITABLE_TABLE_ADD_ROW_SCRIPT` 的验证 root 解析，placeholder 新增入口点击前后必须回到目标 `table_fieldid`、目标列身份或同一表格 cluster。
- [x] 2.2 调整行状态结果，标记验证 root 是否可靠、是否来自目标表格，以及点击前后是否为空态到真实行。
- [x] 2.3 收紧 `_editable_table_add_row_should_retry`，只有可靠目标 root 点击前已有真实数据行且首次点击未增长时才重试。
- [x] 2.4 补全失败诊断，保留首次点击和最终点击的目标表格身份、候选入口、验证 root 摘要和行状态。

## 3. 验证

- [x] 3.1 运行相关聚焦测试，例如 `./.venv/bin/python -m pytest tests/test_runtime.py -q` 中覆盖新增行路径的测试。
- [x] 3.2 运行真实 DSL：`./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/流程-预算管理-调整调剂_财政-待分配预算管理（预算部门）逆向-001.yaml --headless --no-persistent-profile --report-file /tmp/ydf-browser-empty-add-row-placeholder-after-poll.json`，确认 step 7 不再因 placeholder 新增误判失败。
- [x] 3.3 运行 `openspec validate fix-empty-editable-table-add-row-placeholder --strict`。
- [x] 3.4 运行 `./scripts/check_openspec_language.py --change fix-empty-editable-table-add-row-placeholder`。
- [x] 3.5 运行 `git diff --check`。
