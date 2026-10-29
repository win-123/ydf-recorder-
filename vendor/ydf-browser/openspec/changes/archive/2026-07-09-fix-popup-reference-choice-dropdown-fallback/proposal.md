## Why

真实 DSL `/Users/ken/temp/ydf-browser-问题反馈/流程-单位资金分散-单位资金补录全景-保存审核-001.yaml` 在 `form.fill` 填写 `支付业务类型: "1 普通业务"` 时失败。运行时点击字段后页面实际出现普通 `.wui-select-dropdown` 候选，但流程仍等待弹出参照 dialog 并报 `未打开弹出参照选择框`。

现有 `form-choice-field-entry` 已规定普通 choice/dropdown 字段不能因下拉箭头误走 popup reference；这次缺口发生在字段已误入 popup reference 打开流程后的兜底判定，需要补齐。

## What Changes

- 当 `form.fill` 的标量值字段进入 popup reference 打开流程后，如果点击后没有新增弹出参照 dialog，但真实可见普通 choice/dropdown 面板，运行时 SHALL 改用普通下拉候选选择流程。
- 保持结构化弹出参照目标和真正弹出参照字段的既有流程不变。
- 新增回归测试覆盖 `.wui-select-dropdown` 已出现但 popup reference dialog 缺失的 fallback 场景。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `form-choice-field-entry`: 补充普通下拉面板已出现时不得继续报告弹出参照 dialog 缺失的运行时要求。

## Impact

- 影响 `ydf_browser/runtime.py` 中 popup reference 打开后的分流逻辑。
- 影响 `tests/test_runtime.py` 中表单录入、普通下拉和弹出参照边界回归覆盖。
- 不新增 DSL 字段、schema、命令或依赖。
