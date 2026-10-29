## Why

`监督检查方案3.yaml` 在 `内部检查小组` 表格中已经按 `人员名称=财会监督1` 找到目标行，但该表没有 checkbox，当前 `table_row_selection.select` 只尝试勾选行选择框后失败。真实 YonDiF 表格存在“点击行即高亮/选中”的选择模式，这应纳入表格行选择的基础能力。

## What Changes

- 扩展 `table_row_selection.select`：当目标业务行已在指定表格作用域内精确命中，但该行没有可见 checkbox 或等效控件时，runtime 可以点击该业务行触发行高亮/选中。
- 保持优先级不变：有 checkbox 或等效控件时仍优先点击控件，避免误触发表格单元格内链接或编辑入口。
- 保持作用域约束：行点击兜底只在已解析的目标表格作用域内执行，不退回全页面裸文本点击。
- 增强回归覆盖，证明列匹配命中无 checkbox 行时会尝试行点击。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `table-row-selection`: 表格行选择在目标行无 checkbox 时支持点击业务行触发选中/高亮。

## Impact

- 主要影响 `ydf_browser/runtime.py` 的 `table_row_selection.select` 运行时选择分支。
- 需要更新 `openspec/specs/table-row-selection` 的 delta spec。
- 需要新增或调整 `tests/test_runtime.py` 中无 checkbox 行点击的回归测试。
- 不引入新的 DSL 字段，不改变 `table_row_action.click`、`toolbar.click` 或弹出参照选择语义。
