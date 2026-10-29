## Why

普通多选下拉当前只追加目标项，不会移除页面已有默认项，且只要目标文本出现就可能报告成功。真实用例中 `账户状态` 默认选中“启用”，DSL 填写“草稿”后实际形成“启用 + 草稿”，导致查询条件偏离用例意图。

## What Changes

- 为查询区、表单和可编辑表格中的普通多选下拉定义精确赋值语义：标量表示单项集合，列表表示无序目标集合，空列表表示清空全部选中项。
- 在录入前移除目标集合之外的页面默认项或已有项，并补选缺失目标；最终集合存在缺项或额外项时必须失败。
- 按唯一候选项身份匹配目标，允许编码、名称和空白等显示差异；候选匹配不唯一时失败。
- 在 DSL 校验阶段拒绝多选目标列表中的重复值。
- 在成功报告中记录 `expected_values`、`actual_values`，失败时补充 `missing_values`、`unexpected_values`。
- 明确本能力不覆盖 `YDFTreeModalSelect`、`YDFTableModalSelect` 等需要弹窗确认的弹出参照，也不新增追加模式。
- **BREAKING**：普通多选下拉不再保留 DSL 未声明的页面默认项或已有项；依赖旧追加行为的用例需要显式列出完整目标集合。

## Capabilities

### New Capabilities

- `multi-select-dropdown-exact-assignment`: 定义普通多选下拉在查询区、表单和可编辑表格中的目标集合、候选身份匹配、最终集合校验与报告语义。

### Modified Capabilities

无。

## Impact

- 影响普通 choice/dropdown 的 DSL 校验、运行时选择与最终值读取、高层执行结果和结构化报告。
- 预计涉及 `ydf_browser/dsl.py`、`ydf_browser/runtime.py`、`ydf_browser/executor.py` 及对应测试。
- 需要补充 schema/示例，覆盖标量、无序列表、空列表、重复值、默认项移除、集合不一致失败和弹出参照边界。
- 不新增第三方依赖，不修改 YonDiF 页面模板或业务接口。
