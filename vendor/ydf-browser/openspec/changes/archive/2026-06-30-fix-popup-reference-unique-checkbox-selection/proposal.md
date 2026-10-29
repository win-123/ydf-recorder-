## Why

`采购计划编制` 的 `预算项目` 是带 checkbox 的弹出式列表参照。标量短值 `二级采购项目` 能过滤出唯一候选，但运行时把候选行的蓝色高亮误判为业务选中，没有勾选 checkbox，确认时页面提示 `请选择数据！`；同时标量短值命中多条时缺少明确的歧义处理规则。

## What Changes

- 统一弹出参照单目标选择语义：标量值过滤后只有一个可选择候选时选择该候选，零条或多条时明确失败。
- 候选包含可见 checkbox/radio 时，必须验证选择控件真实选中；行焦点或视觉高亮不能替代业务选中态。
- 保留显式选择方式：需要选择第一条时使用 `first_available` 或 `row_number`，需要多选时使用列表或 `selections`。
- 不新增 DSL 字段，不把多条候选默认解释为“第一条”或“全部”。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `popup-reference-tree-table-selection`: 补充标量参照值过滤后的唯一候选选择和歧义失败语义。
- `popup-reference-row-selection-state`: 将 checkbox/radio 真实选中态要求扩展到标量值和 `match` 候选选择路径。

## Impact

- 影响 `ydf_browser/runtime.py` 中弹出参照标量值过滤、候选计数、表格/列表候选点击和选中态验证。
- 影响 `form.fill` 标量弹出参照值及复用同一运行时匹配路径的结构化 `match` 选择。
- 需要在 `tests/test_runtime.py` 增加唯一候选、歧义候选和 checkbox 真实选中态回归测试，并使用原问题 YAML 做真实验证。
- 不新增依赖，不改变现有显式 `first_available`、`row_number`、列表或 `selections` 写法。
