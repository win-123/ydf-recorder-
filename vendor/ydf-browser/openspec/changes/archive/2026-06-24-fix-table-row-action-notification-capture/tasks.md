## 1. 回归测试

- [x] 1.1 在 `tests/test_executor.py` 增加回归：`table_row_action.click` 捕获到 `操作成功` 后，紧随的 `notification.assert` 能匹配 `_last_notifications`。
- [x] 1.2 在 `tests/test_executor.py` 增加保护用例：`table_row_action.click` 捕获到 error notification 且下一步不是 `notification.assert` 时，当前行级动作失败并报告真实错误提示。
- [x] 1.3 在 `tests/test_executor.py` 增加预期错误用例：`table_row_action.click` 捕获 error notification 且下一步是 `notification.assert` 时，行级动作保持成功并由断言步骤校验。

## 2. Executor 实现

- [x] 2.1 调整 `ydf_browser/executor.py` 的 `_execute_table_row_action_click`，在点击行级按钮前启动通知捕获。
- [x] 2.2 行级动作点击、动态模板等待和上下文切换判断完成后收集通知，写入 `_last_notifications`，并在步骤 `data.notifications` 中报告非空提示。
- [x] 2.3 将 `table_row_action.click` 加入点击类动作未处理错误提示保护集合，复用现有 `_unhandled_error_notification_message` 流程。
- [x] 2.4 保持 `row_number`、`match`、`row_search`、`dynamic_template`、`dom_switched_template` 等既有步骤数据不退化。

## 3. 验证

- [x] 3.1 运行 `openspec validate fix-table-row-action-notification-capture --strict`。
- [x] 3.2 运行 `./scripts/check_openspec_language.py --change fix-table-row-action-notification-capture`。
- [x] 3.3 运行聚焦单元测试：`./.venv/bin/python -m pytest tests/test_executor.py`。
- [x] 3.4 使用原始真实用例验证：`./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/功能-网上报销-资金结算-生成支付单.yaml --headless --report-file /tmp/ydf-pay-order-generate-after-row-notification-capture.json`。
- [x] 3.5 运行全量测试：`./.venv/bin/python -m pytest`。
