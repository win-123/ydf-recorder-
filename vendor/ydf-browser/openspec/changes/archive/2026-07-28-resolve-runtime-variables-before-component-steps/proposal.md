## Why

`tree.select` 当前会把 `{{random.suffix}}` 作为字面量传给运行时，导致同一步骤链中已经用于表单录入的随机值无法用于树节点选择。现有运行期变量解析能力已覆盖部分组件，但组件步骤入口不一致，形成同类遗漏风险。

## What Changes

- 在组件步骤执行业务交互前统一解析 `target` 中的运行期变量。
- 保持同一随机变量在不同组件步骤间复用相同缓存值。
- 补充树单选、多选及相邻组件步骤的回归测试。
- 使用真实 DSL 验证保存后的调度单能够按解析后的随机值选择。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `runtime-capture-variables`: 明确组件步骤的完整 `target` 必须在业务交互前完成运行期变量解析，包括 `tree.select` 的单个和多个节点标签。

## Impact

- 主要影响 `ydf_browser/executor.py` 的组件步骤分发与目标读取。
- 补充 `tests/test_executor.py` 的运行期变量回归覆盖。
- 不改变 DSL schema、变量语法、外部依赖或运行时接口。
