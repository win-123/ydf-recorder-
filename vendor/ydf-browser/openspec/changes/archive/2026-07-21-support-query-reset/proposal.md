## Why

`query.search` 只能填写条件并执行查询，查询区“重置”目前只能被误写成不受查询区约束的通用按钮点击，真实用例因此无法绑定该动作。需要提供独立且有明确作用域的查询重置语义，避免误点页面其他同名按钮。

## What Changes

- 新增无参数的 `query.reset` 组件操作，用于恢复当前查询区的初始查询条件。
- 将重置按钮定位限制在唯一的当前前景查询区，优先使用明确的重置身份，其次使用查询区内精确文本，并在歧义或缺失时失败。
- 将 `query.reset` 定义为点击并等待页面稳定的动作，不承诺清除表格勾选，也不强制断言所有查询字段为空。
- 拒绝用 `query.search target.button: 重置` 表达查询重置，并给出迁移提示。
- 同步 DSL schema、中文参考文档、示例、结构化报告和自动化测试，并用真实 DSL 证明直接可见重置按钮可用。

## Capabilities

### New Capabilities

- `query-resetting`: 定义查询区重置的 DSL、作用域、定位、报告、失败和兼容边界。

### Modified Capabilities

无。

## Impact

- DSL 与校验：`ydf_browser/dsl.py`、`schemas/dsl.schema.json`。
- 执行与定位：`ydf_browser/executor.py`、`ydf_browser/runtime.py`、`ydf_browser/adapters.py`。
- 测试与文档：相关 DSL、executor、runtime 测试，以及 README、DSL 参考、能力测试计划和示例。
- 不新增依赖，不改变 `query.search` 的正常查询行为。
