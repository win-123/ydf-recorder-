## Why

`editable_table.add_row` 在空表中点击正确的新增入口并打开行编辑表单后，运行时仍因目标表格没有立即增行而提前失败，并误报“未点击新增”。这会阻断显式声明 `target.editor: form` 的既有业务流程，也可能让同一新增入口在主 frame 与 page 上被重复执行。

## What Changes

- 将“已点击新增但目标表格尚未增行”保留为结构化运行时结果，不再在 runtime 层丢失点击、候选和行状态证据。
- 由 executor 统一判断新增完成信号：目标表格真实增行或行编辑表单模板打开均可成功；两者都未发生时保持失败。
- 在首次点击已经产生页面副作用后停止继续扫描其它搜索上下文，避免重复点击同一新增入口。
- 补充空表 `editor: form`、空表无完成信号和单次点击的回归覆盖。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `editable-table-cell-entry`: 明确空表新增打开行编辑表单模板时的成功语义，以及点击后不得跨重复搜索上下文再次执行新增的约束。

## Impact

- 影响 `ydf_browser/runtime.py` 的可编辑表格新增结果与搜索上下文收口。
- 影响 `ydf_browser/executor.py` 的新增完成信号判定和失败诊断。
- 补充 `tests/test_runtime.py`、`tests/test_executor.py` 聚焦回归，并用原始真实 DSL 复验。
