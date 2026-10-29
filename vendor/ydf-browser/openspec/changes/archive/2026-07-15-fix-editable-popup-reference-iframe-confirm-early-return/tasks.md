## 1. 回归测试

- [x] 1.1 在 `tests/test_runtime.py` 增加失败回归，复现候选已选中、参照字段根出现临时值、目标单元格仍为占位文本且 iframe 候选面仍可见时，不得以 `target-backfill` 提前返回。
- [x] 1.2 增加旧参照 locator 不可读但当前搜索上下文仍存在候选表格、确认动作和取消动作的回归，验证运行时继续进入确认路径。
- [x] 1.3 保持既有自动关闭且已回填、iframe 表单参照确认、背景页面保存隔离和 checkbox/radio 真实选中态测试通过。

## 2. 共享运行时修复

- [x] 2.1 调整 `ydf_browser/runtime.py` 的共享弹出参照隐藏判断：旧 locator 不可读时继续检查当前页面和所有子 frame 的有效候选参照面，不增加页面、字段或菜单专用分支。
- [x] 2.2 收紧 `target-backfill` 早退条件，使仍可见的候选参照继续复用 `_click_popup_reference_confirm*()`，并由目标单元格回填等待完成最终判定。
- [x] 2.3 保持 `close_action`、`confirmed`、`confirm_label`、候选选中态和失败截图诊断稳定，确保报告能区分提前返回、确认完成和最终未回填。

## 3. 验证

- [x] 3.1 运行新增测试及相邻 popup reference、editable table 聚焦测试，确认回归先失败后通过。
- [x] 3.2 使用当前源码执行原始真实 DSL 的 `batch_payment_apply_decentral` 用例并输出独立报告，确认第 7 步 `editable_table.fill_row` 成功完成且 `收款人全称` 已真实回填。
- [x] 3.3 检查真实报告中的候选选中态、`confirmed`、`confirm_label`、`close_action`、frame 和字段回填证据；后续独立业务数据失败不得扩大本 change 范围。
- [x] 3.4 运行完整 `./.venv/bin/python -m pytest`，覆盖共享 runtime 改动的相邻 DSL 形式。
- [x] 3.5 运行 `openspec validate fix-editable-popup-reference-iframe-confirm-early-return --strict`、`./scripts/check_openspec_language.py --change fix-editable-popup-reference-iframe-confirm-early-return` 和 `git diff --check`。
