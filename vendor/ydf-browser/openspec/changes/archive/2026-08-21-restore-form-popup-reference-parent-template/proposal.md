## Why

`form.fill` 内完成弹出参照选择后，运行时可能应用参照弹窗的动态模板却未恢复父表单模板，导致后续可编辑表格动作仍在已关闭弹窗的 manifest 中绑定并错误报告“表格名称未匹配”。需要在保留身份与可见性校验的前提下恢复父模板，同时避免没有应用弹窗模板时误退回更早页面。

## What Changes

- 当 `form.fill` 已完成弹出参照且本次填充确实应用了 post-fill 动态模板时，允许现有父模板恢复判定恢复到表单模板。
- 当前模板上下文来自 `form.fill` 但没有应用 post-fill 动态模板、弹窗未确认关闭或父模板证据不足时继续 fail-closed，不弹出模板栈。
- 增加单元回归和无保存、无提交的最小真实 DSL 回归，证明后续“合同付款计划”新增行可绑定到当前编辑页。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `dynamic-template-context-restoration`: 补充 `form.fill` 内弹出参照完成后的父模板恢复条件与 fail-closed 边界。

## Impact

- 运行时：`ydf_browser/executor.py` 的表单弹出参照模板恢复入口。
- 验证：`tests/test_executor.py` 与 `tests/real_cases/`。
- DSL schema、字段和外部依赖不变。
