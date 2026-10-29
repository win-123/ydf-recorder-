## 1. 聚焦复现和测试

- [x] 1.1 从现有报告确认失败链路：第一次 `editable_table.add_row` 成功，`editable_table.fill_row` 成功，第二次 `editable_table.add_row` 在 `table_fieldid=cgbd_table` 上 `before_rows=1; after_rows=1`。
- [x] 1.2 为 `PlaywrightRuntime.add_editable_table_row` 增加聚焦测试，覆盖目标表格已有 1 行、首次点击未增长、收口后同一目标表格重试增长的路径。
- [x] 1.3 增加失败路径测试，覆盖首次点击和一次重试后仍未增长时继续报告新增行未生效，并保留行数和目标表格诊断。

## 2. Runtime 实现

- [x] 2.1 在 `ydf_browser/runtime.py` 的共享新增入口增加点击前交互收口，处理 active element blur、focusout/blur、可见选择下拉和行级悬浮/更多按钮残留状态。
- [x] 2.2 当目标表格解析出 `table_fieldid` 时，优先使用 `${table_fieldid}_add_button` 对应的可见 fieldid 入口定位新增按钮，未命中时再走通用候选扫描。
- [x] 2.3 调整 add-row runtime 脚本或 Python 包装逻辑，让非空目标表格首次点击未增长时只在同一目标表格作用域内重试一次。
- [x] 2.4 过滤行级、sticky 表格副本等非新增行入口候选，避免连续填行后误点已有数据行旁的 `新增` 动作。
- [x] 2.5 保留现有目标表格限定验证和失败门禁：目标表格行数未增长且没有动态模板时仍失败，不把同一行交给后续 `editable_table.fill_row`。
- [x] 2.6 在步骤结果或错误诊断中保留首次和最终 row_state、目标表格身份和可用候选摘要，便于判断点击是否被页面吞掉。

## 3. 验证

- [x] 3.1 运行相关聚焦测试，例如 `./.venv/bin/python -m pytest tests/test_runtime.py -q` 中覆盖本变更的测试。
- [x] 3.2 运行真实 DSL：`./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/14功能-预算执行-采购管理-采购需求编制-新增提交-0001.yaml --headless --report-file <report.json>`，确认第二次新增和后续填行通过。
- [x] 3.3 运行真实 DSL 默认 headed 路径：`./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/14功能-预算执行-采购管理-采购需求编制-新增提交-0001.yaml --report-file <report.json>`，确认两次新增均走 `table-fieldid-add-button` 且完整提交通过。
- [x] 3.4 按共享 runtime 改动风险运行完整 `./.venv/bin/python -m pytest`。
- [x] 3.5 运行 `openspec validate stabilize-repeat-editable-table-add-row --strict`、`./scripts/check_openspec_language.py --change stabilize-repeat-editable-table-add-row` 和 `git diff --check`。
