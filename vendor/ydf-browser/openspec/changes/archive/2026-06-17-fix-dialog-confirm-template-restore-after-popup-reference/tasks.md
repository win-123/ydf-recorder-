## 1. Reproduction and Guard Tests

- [x] 1.1 保留当前真实失败报告线索，确认 `/tmp/ydf-pay-order-save-missing-report.json` 中第 5 步 `dialog.confirm` 自动恢复到 root，且第 6 步 `toolbar.click 保存` 失败为 `未绑定工具栏动作: 保存`。
- [x] 1.2 在 `tests/test_executor.py` 增加回归：`table_row_action.click 编辑` 后的动态编辑模板仍有 `保存`，执行 `popup_reference.select` 和 `dialog.confirm 确定` 后不得自动恢复上一层列表模板。
- [x] 1.3 在 `tests/test_executor.py` 保留或补充正向回归：当 `dialog.confirm` 后当前动态模板稳定动作消失且上一层列表可见时，仍应自动恢复上一层列表模板。

## 2. Executor Restore Logic

- [x] 2.1 收窄 `_should_auto_restore_previous_template_after_dialog_confirm()`，在恢复前检查当前动态 manifest 是否仍有可见的稳定表单动作身份，例如 `保存`、`提交`、`取消`、`确定`、`确认`。
- [x] 2.2 复用现有 `_manifest_has_visible_action_identity` / `_manifest_visible_action_identity_matches` 和 `_manifest_visibility_score`，避免新增与 popup/form 参照恢复不一致的 DOM 判断。
- [x] 2.3 确保未恢复时 `dialog.confirm` step data 不写入 `auto_restored_template: true`，恢复时继续保留 `restored_template` 和 `auto_restored_template: true`。

## 3. Verification

- [x] 3.1 运行新增和相关 executor 单元测试，确认失败场景变绿且真实返回列表场景不退化。
- [x] 3.2 运行真实用例 `/Users/ken/temp/ydf-browser-问题反馈/功能-网上报销-资金结算-生成支付单-按钮-0020.yaml`，确认第 6 步不再因 `未绑定工具栏动作: 保存` 失败；若后续业务步骤失败，记录新的首个失败点。
- [x] 3.3 运行 `openspec validate fix-dialog-confirm-template-restore-after-popup-reference --strict`。
- [x] 3.4 运行项目全量测试套件，确认无回归。
