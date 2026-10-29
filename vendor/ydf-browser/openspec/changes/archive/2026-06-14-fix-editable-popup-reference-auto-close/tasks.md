## 1. 回归测试

- [x] 1.1 在 `tests/test_runtime.py` 增加单测，复现可编辑表格 `YDFReferSelect` 选择后目标单元格已回填、候选层已消失、背景编辑页仍有 `保存` 按钮时，运行时不得继续查找参照确认按钮。
- [x] 1.2 增加单测覆盖参照候选层关闭但目标单元格未回填时，应失败为“参照选择未回填”，而不是“未找到弹出参照确认按钮”。
- [x] 1.3 增加单测保护既有行为：当前活动参照根仍包含候选区和页脚 `保存` 时，`保存` 仍可作为弹出参照确认按钮。

## 2. 运行时修复

- [x] 2.1 调整 `ydf_browser/runtime.py` 中弹出参照可见性判断，区分真实参照候选层与背景编辑页按钮，避免页面级 `保存` 让旧参照根误判为仍可见。
- [x] 2.2 调整可编辑表格参照列录入收口逻辑：选择候选后若目标单元格已回填且候选层已关闭，应记录结果并返回成功。
- [x] 2.3 保持参照根内 `保存/取消` 弹窗的确认能力，确认按钮查找必须限定在当前活动参照根内。
- [x] 2.4 改善失败诊断，确保候选层关闭但未回填时错误指向回填缺失，并保留页面 warning/notification 作为辅助诊断。

## 3. 验证

- [x] 3.1 运行聚焦单测，例如 `./.venv/bin/python -m pytest tests/test_runtime.py -k "popup_reference or editable_popup_reference"`。
- [x] 3.2 运行 OpenSpec 校验：`openspec validate fix-editable-popup-reference-auto-close --strict`。
- [x] 3.3 使用源码入口真实执行 `/Users/ken/temp/ydf-browser-问题反馈/功能-网上报销-报销管理-还款单填报-按钮-0011.yaml`，报告写入 `/tmp/ydf-hkdtb-0011-after-fix-report.json`。
- [x] 3.4 检查真实报告，确认第 7 步 `editable_table.fill_row` 已越过 `汇款转账.收款方户名`；如果后续 `保存` 因 `退回金额不允许大于可用金额` 等业务数据 warning 失败，应在交付说明中单独标注。
