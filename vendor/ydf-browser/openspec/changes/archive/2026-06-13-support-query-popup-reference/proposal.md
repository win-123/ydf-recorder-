## Why

`申报项目模板设置` 的查询条件 `项目目录` 是 `YDFTreeModalSelect` 弹出参照，但当前 `query.search` 只按文本框或普通下拉/树下拉处理，导致运行时把弹出参照误走成 dropdown 选择并失败。

这个问题会影响预算绩效等页面中“查询条件本身是参照控件”的用例，尤其是项目目录这类可多选查询条件。

## What Changes

- 让 `query.search` 在查询字段元数据或运行时 DOM 表明字段是 `YDFTreeModalSelect`、`YDFTableModalSelect`、`YDFReferSelect` 或 refer/modal 参照时，复用弹出参照选择流程。
- 保持普通文本框、普通下拉、树形下拉查询条件的现有行为不变。
- 保留 `equals` 的原始值类型，支持标量、列表和结构化参照目标进入运行时，而不是在执行器中过早字符串化。
- 在步骤结果中记录查询条件参照选择的 `selected`、`confirmed`、`confirm_label`、`popup_tree_context` 等诊断信息。
- 补充 DSL 文档、示例和回归测试，覆盖 `项目目录` 查询条件弹出参照以及多选值。

## Capabilities

### New Capabilities

- `query-popup-reference-selection`: 描述查询条件字段为弹出参照时的 DSL、运行时分流、多选选择和步骤报告行为。

### Modified Capabilities

- 无。

## Impact

- 影响 `ydf_browser/executor.py` 中 `query.search` 条件值传递和步骤结果组装。
- 影响 `ydf_browser/runtime.py` 中 `fill_query_field` 的查询字段类型分流。
- 影响 DSL 文档和使用指南中 `query.search` 的查询条件控件说明。
- 需要新增或扩展单元测试，重点覆盖查询字段 `YDFTreeModalSelect` 不再误走下拉、普通 `YDFTreeSelect` 查询仍走下拉树、多选 `equals` 不被字符串化。
- 不引入新依赖，不改变登录、菜单打开、表单字段参照、独立 `popup_reference.select` 或页面左树选择语义。
