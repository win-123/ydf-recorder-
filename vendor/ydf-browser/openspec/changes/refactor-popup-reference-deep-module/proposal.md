## Why

`PlaywrightRuntime` 当前承载约 5,500 行弹出参照流程，四条高层路径通过私有方法和可变 side channel 共享行为，导致变更、诊断和测试分散在超大 `runtime.py` 与实现耦合测试中。平台渲染契约基线已经归档，现在可以在不改变 DSL、报告和完成语义的前提下，把该高复杂度流程收敛到一个可独立验证的 deep module。

## What Changes

- 新增 `ydf_browser.popup_reference` deep module，以 `PopupReference.select(request) -> PopupReferenceResult` 作为唯一有副作用的公开操作。
- 将弹出参照的来源恢复、触发、候选面解析、目标选择、确认、完成验证和专属诊断从 `PlaywrightRuntime` 移入该 module。
- 让表单、查询、可编辑表格和已打开弹出参照四条路径构造稳定请求并复用同一个 implementation。
- 用不可变结果和 `PopupReferenceError` 替代 `last_popup_reference_result` side channel，并由 Runtime adapter 映射为现有返回字典。
- 将测试迁移到公开 module interface；Runtime 和 executor 测试只保留分派、映射、报告及模板恢复职责。
- 删除 runtime 中旧委托、弹出参照专属私有流程、目标规范化函数和已被 interface tests 替代的私有实现测试。
- 不改变 DSL schema、步骤报告字段、通用原因码、`PRS-POPUP-001/002` 契约路径或现有完成语义。

## Capabilities

### New Capabilities

无。本变更只调整内部 module 和 seam，不引入用户可见能力。

### Modified Capabilities

无。现有 `popup-reference-tree-table-selection`、`popup-reference-row-selection-state`、`query-popup-reference-selection`、`form-field-entry`、`editable-table-cell-entry` 和 `dynamic-template-context-restoration` requirements 保持不变。

## Impact

- 主要代码：`ydf_browser/runtime.py`、`ydf_browser/executor.py`、新增 `ydf_browser/popup_reference/`。
- 主要测试：新增 `tests/popup_reference/`，收窄 `tests/test_runtime.py` 和 `tests/test_executor.py`。
- 外部兼容性：DSL、报告、契约路径、真实页面行为和第三方依赖保持不变。
- 迁移风险：弹出参照覆盖 modal、drawer、frame、树、表格、列表及自动关闭等多种运行时形态，需要聚焦测试、全量 pytest 和两条真实 DSL 共同验证。
