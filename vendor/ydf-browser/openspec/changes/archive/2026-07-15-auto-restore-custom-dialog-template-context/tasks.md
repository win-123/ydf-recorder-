## 1. 回归测试

- [x] 1.1 在 `tests/test_executor.py` 增加自定义 `dialog.click` 关闭动态模板后仍错误保留子 manifest 的失败测试，并确认修复前稳定失败。
- [x] 1.2 增加当前动态表单仍活跃、出现错误通知和父模板证据不足时不自动恢复的保护测试。

## 2. 最小实现

- [x] 2.1 在 `ydf_browser/executor.py` 复用现有 manifest 栈、稳定身份和可见性判断，为未命中固定标签分支的 `dialog.click` 增加受保护的 DOM 转场恢复。
- [x] 2.2 成功恢复时写入 `restored_template` 和 `auto_restored_template: true`，不满足恢复条件时保持现有步骤结果与当前 manifest。

## 3. 验证

- [x] 3.1 运行相关 `tests/test_executor.py` 聚焦测试，覆盖自定义动作恢复和既有保存、确认恢复行为。
- [x] 3.2 使用当前源码运行用户提供的真实 DSL 用例 `batch_payment_apply_decentral`，确认“去签章”步骤记录自动恢复，且后续父列表表格操作不再按 `inc_payee_table` 解析并最终通过。
- [x] 3.3 运行完整 `./.venv/bin/python -m pytest`、`openspec validate auto-restore-custom-dialog-template-context --strict`、`./scripts/check_openspec_language.py --change auto-restore-custom-dialog-template-context` 和 `git diff --check`。
