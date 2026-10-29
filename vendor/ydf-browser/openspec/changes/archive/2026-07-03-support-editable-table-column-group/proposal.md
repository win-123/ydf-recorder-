## Why

多表头可编辑表格允许不同父表头下出现相同明细列名。现有 `editable_table.fill_row` 只能按明细列名匹配，遇到同名叶子列时会默认命中第一个可见列，可能点到只读列或错误业务列。

需要让 DSL 能在保持普通列简洁写法的同时，为歧义列声明父表头限定，并继续通过模板列身份和真实 DOM 诊断证明写入目标列。

## What Changes

- `editable_table.fill_row` 的 `target.fields` 对象写法支持字段值包装器：字段值为对象且包含 `column_group` 时，`value` 或 `equals` 表示实际录入值，`column_group` 表示目标列所属父表头。
- `column_group` 支持字符串或字符串列表；字符串表示单级父表头，列表表示从外到内的多级父表头路径。
- 保持普通 `fields` 对象写法不变；只有同名列或需要消歧的列才需要包装器。
- `fields` 列表写法也支持 `column_group`，作为同一步骤中需要重复填写同一叶子列名等极端场景的等价表达。
- 当同一目标表格内存在多个同名叶子列且 DSL 未提供足够父表头限定时，步骤必须失败并提示可用父表头路径，不能默认写入第一个同名列。
- 更新用户文档和示例，说明普通列、带父表头列、结构化参照值与 `column_group` 的组合写法。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `editable-table-cell-entry`: 扩展可编辑表格字段定位契约，支持按父表头限定同名明细列，并补充歧义失败和诊断要求。

## Impact

- 影响 `ydf_browser/dsl.py` 对 `editable_table.fill_row target.fields` 的校验和字段值包装器识别。
- 影响 `ydf_browser/executor.py` 从 DSL 字段项提取列名、父表头限定和实际录入值，并选择唯一模板列候选。
- 影响 `ydf_browser/template_parser.py` 或相关模型对多级表头父子关系、父表头路径的保留。
- 影响 `ydf_browser/runtime.py` 在模板身份不足时按 DOM 多表头路径做文本几何兜底，并在失败诊断中暴露可用路径。
- 需要补充 `tests/test_dsl.py`、`tests/test_executor.py`、`tests/test_template_parser.py`、`tests/test_runtime.py` 的窄回归。
- 需要更新 README、`docs/action-capability-test-plan.md` 或相关示例 YAML，覆盖 `column_group` 推荐写法和真实问题用例。
