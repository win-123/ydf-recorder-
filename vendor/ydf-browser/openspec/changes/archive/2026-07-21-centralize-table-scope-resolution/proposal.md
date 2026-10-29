## Why

表格类 DSL 动作目前在 executor 与 runtime 中分别解析表格名称、`table_fieldid`、列归属、前景可见性和实际 DOM 根，导致同一目标在不同动作中可能采用不同兜底规则。近期多次表格作用域修复表明这条 seam 缺少统一事实源，既增加误操作风险，也使诊断和测试分散。

## What Changes

- 新增统一的表格作用域解析能力，在动作执行前集中解析 DSL 目标、manifest 表格身份、运行时前景根、必需列和诊断证据。
- 将显式 `table_fieldid` 视为硬约束；目标不存在、不可交互或列语义冲突时失败，不回退到同名表格。
- 在未提供 `table_fieldid` 时仅接受证据唯一的表格候选；多个可见候选不得通过评分或顺序自动消歧。
- 将前景交互上下文作为硬作用域，并以真实可见、可交互的运行时 DOM 作为最终事实源，同时记录 manifest 差异。
- 每个表格类步骤重新解析作用域；动作尚未产生页面副作用且 DOM 根失效时，统一解析能力最多重试一次。
- 成功报告保留紧凑表格身份与列证据，失败和调试报告保留完整候选及排除原因。
- 首期覆盖主表、可编辑表格和树形表格对应的表格行选择、表格断言、行级动作、单元格链接、新增行和录入；不包含弹出参照内部候选表格，也不接管行匹配或行选择执行。
- **BREAKING**：过去依赖同名首选、候选评分、背景表格兜底或缺列后继续执行的 DSL 可能改为在动作前明确失败。

## Capabilities

### New Capabilities
- `table-scope-resolution`: 定义所有表格类 DSL 动作共享的表格身份、前景作用域、列预校验、运行时事实源、刷新和诊断语义。

### Modified Capabilities
- `table-row-selection`: 行选择必须消费统一表格作用域，不得在 runtime 中按旧参数另行查找其它表格。
- `table-column-assertions`: 列集合、列值和行值断言必须在执行前解析唯一表格并校验必需列。
- `table-row-action-clicking`: 行级动作未指定表格时只允许唯一作用域，不再以目标行唯一作为跨表格兜底。
- `table-cell-link-clicking`: 单元格链接点击必须使用统一表格作用域和必需列预校验。
- `editable-table-cell-entry`: 可编辑表格新增行和录入必须使用统一作用域身份、前景规则和失效重试语义。

## Impact

- 主要影响 `ydf_browser/executor.py`、`ydf_browser/runtime.py`、`ydf_browser/models.py` 及新增的表格作用域 module。
- 需要迁移 `tests/test_executor.py`、`tests/test_runtime.py` 中依赖私有解析 helper 的测试，并新增以 module interface 为测试面的聚焦测试。
- DSL schema 不新增字段，但既有 `target.table`、`table_fieldid` 和动作引用列的解释更严格。
- 报告中的表格身份和作用域诊断将统一；不新增第三方依赖。
