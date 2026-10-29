## Why

经费申请单选择指标后，候选行已勾选，但运行时把仍可见的参照误判为关闭，跳过确定并让后续点击被遮挡。原因是候选表格在 iframe 内，而确认按钮在外层弹窗。

## What Changes

- 在共享关闭判定中识别外层弹窗的可见 iframe 候选承载，保留外层确认动作。
- 增加真实浏览器回归和不保存、不提交的真实 DSL。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `popup-reference-tree-table-selection`：补充候选表格与确认按钮分属 iframe 内外的完成判定。

## Impact

仅修改弹出参照共享完成判定，覆盖独立选择、表单、查询和可编辑表格入口；不增加 DSL 字段或依赖。
