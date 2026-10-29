## Why

`功能-单位收入管理-来款认领-项目认领-补开发票-002` 真实执行时，发票弹窗内 `发票内容明细.商品` 使用 `first_available: true` 选择商品参照失败；截图中前景商品弹窗已有 1 条真实业务行，但运行时候选诊断只尝试了来自右表的空状态文本，导致没有选中可见商品行。

这会让 `editable_table.fill_row` 对 `YDFTableModalSelect` 的第一条可用候选选择不可靠：业务可选数据已经出现，工具却把候选识别偏到空状态、固定列副本或非业务候选。

## What Changes

- 收紧 `popup_reference first_available` 的候选发现：可见业务表格行存在时，运行时 MUST 优先识别并点击该业务行或其 radio/checkbox 控件。
- `first_available` 候选集合 MUST 排除 `暂无数据`、`暂时没有数据`、查询空态、表头、查询区、分页、footer 等非业务行。
- 当候选诊断同时能读到真实业务行文本和空状态候选时，运行时 MUST 不得只尝试空状态候选后失败。
- 可编辑表格参照列失败诊断继续保留候选数量、候选来源、候选文本和截图，方便区分业务无数据与运行时 DOM 识别失败。
- 不新增 DSL 字段，不要求用户把 `first_available` 改写成 `filter + match`。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `popup-reference-row-selection-state`: 补充 `first_available` 候选发现和空状态排除规则，确保带选择控件的可见业务表格行能被真实选中。
- `editable-table-cell-entry`: 补充可编辑表格参照列使用 `first_available` 时的业务行优先和失败诊断要求。

## Impact

- 影响 `ydf_browser/runtime.py` 中弹出参照 `first_available` 候选采集、排序、过滤和选中态校验。
- 影响 `editable_table.fill_row` 结构化参照字段的字段级结果与错误诊断。
- 需要补充 `tests/test_runtime.py` 中覆盖空状态候选与真实业务行同时存在时必须选择业务行的回归。
- 需要用真实 YAML `/Users/ken/temp/ydf-browser-问题反馈/功能-单位收入管理-来款认领-项目认领-补开发票-002.yaml` 验证步骤 8 能选中商品行并继续执行到后续独立校验点。
