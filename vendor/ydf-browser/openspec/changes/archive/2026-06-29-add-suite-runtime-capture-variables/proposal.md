## Why

当前 DSL 只能在执行前解析外部变量，无法在用例执行过程中把页面生成的业务唯一标识保存下来并供后续用例使用。预算执行业务里单据号、项目代码等字段通常在保存后由后端生成，提交、审核、终审等跨用例链路需要稳定引用这些运行期值，因此需要引入 suite 级运行期变量和表格行值捕获能力。

## What Changes

- 新增 `table.capture_row_values` 组件操作，用于从按 `match` 定位到的表格行中读取指定列值，并写入运行期变量。
- 新增 suite 级运行期变量上下文，允许同一 suite 内后续 case 使用前序 case 捕获的变量。
- 变量引用继续使用 `{{变量名}}` 语法，但捕获变量在步骤执行前由运行期上下文解析，不再要求在 DSL 加载阶段存在。
- 推荐 DSL 写法为 `target.capture`，语义是 `变量名: 页面列名`，例如 `project.code: 项目代码`。
- 包含运行期捕获或运行期变量引用的 suite 必须按用例顺序串行执行，避免并发 case 读取未写入的变量。
- 捕获步骤和变量解析失败必须进入报告，记录匹配条件、来源列、目标变量名和实际捕获值，便于审计和排查。

## Capabilities

### New Capabilities
- `runtime-capture-variables`: 定义运行期变量解析、suite 级变量作用域、变量未定义失败、串行执行约束和报告审计语义。
- `table-row-value-capture`: 定义 `table.capture_row_values` 的 DSL 结构、表格行定位、列值采集、捕获变量写入和诊断语义。

### Modified Capabilities
- 无。新能力会复用 `table-row-selection` 的表格作用域、行定位和树形表格查找能力，也会沿用现有外部变量来源和优先级，但不改变这些既有 capability 的需求语义。

## Impact

- 受影响代码主要包括 `ydf_browser/dsl.py`、`ydf_browser/variables.py`、`ydf_browser/executor.py`、`ydf_browser/runtime.py`、`ydf_browser/runner.py` 和报告结构。
- 需要新增或扩展 DSL 校验，允许 `table.capture_row_values target.capture`，并禁止不明确的捕获目标。
- 需要复用现有 `collect_table_row_values` 能力，避免新增裸 DOM selector 语义。
- 需要在 suite 运行编排中为运行期变量提供共享上下文，并在必要时限制同一 suite 并发调度。
- 需要补充单元测试覆盖 DSL 校验、变量解析、捕获执行、跨 case 共享、并发约束和报告数据。
