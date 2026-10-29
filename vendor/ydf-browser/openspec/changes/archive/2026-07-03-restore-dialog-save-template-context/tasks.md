## 1. 回归测试

- [x] 1.1 增加 executor 单测，复现列表 -> 动态表单 -> 动态弹窗中 `dialog.click 保存` 未恢复上一层导致后续 `提交` 失效的问题。
- [x] 1.2 先运行新增单测，确认失败原因是 `dialog.click 保存` 未自动恢复模板。

## 2. 实现

- [x] 2.1 在 `dialog.click` 后处理里复用保存后自动恢复判断，仅覆盖 label 为 `保存` 或 `提交` 的场景。
- [x] 2.2 运行新增单测，确认多层模板恢复顺序通过。

## 3. 验证

- [x] 3.1 运行 `openspec validate restore-dialog-save-template-context --strict` 和 `./scripts/check_openspec_language.py --change restore-dialog-save-template-context`。
- [x] 3.2 重跑真实 DSL `/Users/ken/temp/ydf-browser-问题反馈/功能-单位收入管理-来款认领-项目认领-补开发票-002.yaml`，确认原始的第 15 步 `提交` 模板阻断已被修复；真实 DSL 随后暴露独立的第 14 步表格名不匹配。
- [x] 3.3 运行相关 focused pytest 和全量 pytest。
