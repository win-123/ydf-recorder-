## Why

表格类 DSL 步骤解析作用域时会扫描主页面和子 frame；任一辅助 frame 恰好发生导航，Playwright 的 `Frame.evaluate` 异常会中断整个步骤，即使目标表格仍在稳定的业务上下文中可用。该竞态已在真实 DSL 中出现，需要将单个运行时上下文的瞬时失败与目标表格不可用区分开。

## What Changes

- 表格作用域检查在扫描前景状态、表格证据和执行令牌时，隔离单个运行时上下文的瞬时求值失败，并继续使用其余稳定上下文。
- 当稳定上下文仍能提供唯一、可见、可交互的目标表格证据时，表格类步骤继续执行既有作用域解析和动作语义。
- 增加回归测试和真实 DSL 验证，证明辅助 frame 导航不会掩盖目标表格证据。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `table-scope-resolution`: 明确单个运行时上下文瞬时不可求值时的隔离语义，避免无关 frame 导航使稳定目标表格的作用域解析失败。

## Impact

- 运行时：`PlaywrightRuntime.inspect_table_scope_regions` 和 `PlaywrightRuntime.is_table_scope_token_valid`。
- 测试：表格作用域运行时证据与执行令牌验证用例。
- DSL schema、动作字段和报告结构均不变化；不新增依赖。
