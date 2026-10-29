## 1. 回归测试

- [x] 1.1 在 `tests/test_executor.py` 增加保存后子表单关闭、上一层表格模板可见时自动恢复的用例。
- [x] 1.2 增加保存失败出现 error notification 时不得自动恢复的保护用例。
- [x] 1.3 保留或补强保存后子表单仍可见时不得因背景模板可见而误恢复的用例。

## 2. 运行时恢复逻辑

- [x] 2.1 调整 `ydf_browser/executor.py` 中保存/提交后的恢复判断，使用当前模板关键动作/字段是否仍作为前景可操作面存在来判断是否恢复。
- [x] 2.2 保持 `restore_previous` 显式配置兼容，并继续在报告中输出 `restored_template` / `auto_restored_template`。
- [x] 2.3 如保存后主判断未恢复但下一步表格操作发现当前模板无表格、上一层模板有可见表格，增加一次窄范围兜底恢复。

## 3. 验证

- [x] 3.1 运行 `openspec validate auto-restore-closed-dynamic-template-after-save --strict`。
- [x] 3.2 运行 `./scripts/check_openspec_language.py --change auto-restore-closed-dynamic-template-after-save`。
- [x] 3.3 运行相关单元测试：`./.venv/bin/python -m pytest tests/test_executor.py`。
- [x] 3.4 使用原始真实用例验证：`./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/监督检查方案2.yaml --headless --report-file /tmp/ydf-supervision-plan2-auto-restore-report.json`。
- [x] 3.5 运行全量测试：`./.venv/bin/python -m pytest`。
