## 1. 诊断和规格补齐

- [x] 1.1 使用真实 DSL `/Users/ken/temp/ydf-browser-问题反馈/流程-单位资金分散-单位资金补录全景-保存审核-001.yaml` 复现 `支付业务类型` 被误报为弹出参照 dialog 缺失的问题。
- [x] 1.2 确认真实运行时已出现 `.wui-select-dropdown` 普通下拉候选，问题属于 `form-choice-field-entry` 的运行时兜底缺口。
- [x] 1.3 补充 OpenSpec proposal、design 和 `form-choice-field-entry` delta spec。

## 2. 实现和测试

- [x] 2.1 在 `_select_popup_reference()` 中补充标量值、普通下拉可见且无新增 dialog 时的 choice/dropdown fallback。
- [x] 2.2 新增 `test_playwright_runtime_popup_reference_falls_back_to_visible_choice_dropdown` 回归测试。
- [x] 2.3 运行相邻表单 choice、LCDEnum、modal select、refuri select 分流测试，确认没有破坏既有边界。

## 3. 验证和交付

- [x] 3.1 运行 `./.venv/bin/python -m pytest tests/test_runtime.py -q`。
- [x] 3.2 运行真实 DSL，确认原 `支付业务类型` 的 `未打开弹出参照选择框` 错误消失，并记录后续 `开户银行` 绑定问题不属于本 change。
- [x] 3.3 运行完整 `./.venv/bin/python -m pytest -q` 和 `git diff --check`。
