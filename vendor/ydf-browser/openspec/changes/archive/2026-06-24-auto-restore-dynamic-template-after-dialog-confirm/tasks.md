## 1. 回归测试

- [x] 1.1 在 `tests/test_executor.py` 增加 `toolbar.click` 打开动态弹窗、`dialog.confirm` 返回列表、后续 `query.search` 成功的回归用例。
- [x] 1.2 增加确认后当前动态表单仍可见时不得自动恢复的保护用例。
- [x] 1.3 增加确认后出现 error notification 时不得自动恢复的保护用例。

## 2. 运行时恢复逻辑

- [x] 2.1 调整 `ydf_browser/executor.py` 中 `dialog.confirm` 后的自动恢复判定，覆盖 `toolbar.click` 打开的动态模板。
- [x] 2.2 复用现有上一层模板可见性、当前模板稳定动作/字段、错误通知保护逻辑，避免页面特例。
- [x] 2.3 保持显式 `restore_previous` 兼容，并继续在自动恢复时输出 `restored_template` / `auto_restored_template`。

## 3. 验证

- [x] 3.1 运行 `openspec validate auto-restore-dynamic-template-after-dialog-confirm --strict`。
- [x] 3.2 运行 `./scripts/check_openspec_language.py --change auto-restore-dynamic-template-after-dialog-confirm`。
- [x] 3.3 运行相关单元测试：`./.venv/bin/python -m pytest tests/test_executor.py`。
- [x] 3.4 使用原始真实用例验证：`./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-项目库-YDF-82797-0001-执行项目新增父子项目和设置经费管理员new.yaml --headless --report-file /tmp/ydf-exec-project-dialog-confirm-restore-report.json`。
- [x] 3.5 运行全量测试：`./.venv/bin/python -m pytest`。
