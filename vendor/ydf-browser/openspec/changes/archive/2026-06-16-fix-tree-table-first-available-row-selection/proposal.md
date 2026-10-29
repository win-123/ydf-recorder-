## Why

真实用例 `/Users/ken/temp/ydf-browser-问题反馈/实物管理-易耗品物资-入库填报-新增-0001 2.yaml` 使用 `物资分类: {tree: {label: A05040101 复印纸}, first_available: true}` 时，运行时将 `editable_table.fill_row` 判定为成功，但保存失败为 `物资入库第1行物资名称不能为空`。这说明当前 `first_available` 在树表弹出参照中可能只让当前 `物资分类/materialTypeName` 单元格回填，没有等价于手工点击右侧物资候选行并带出 `物资名称/materialItemName` 等同一行字段。

调试日志进一步显示 `popup-reference-first-candidate` 首个候选 `requires_selection=False`，而右侧候选表格行应要求选择态；当前成功标准和诊断都不足以区分“点中了右表物资行”和“点中了左树或普通文本后当前格有值”。

## What Changes

- 修正树表弹出参照中 `tree + first_available` 的候选选择语义：应用左树上下文后，必须优先选择右侧候选表格中的第一条有效数据行。
- 如果当前活动弹窗包含右侧候选表格，但 `first_available` 未能选中可确认的数据行，当前字段必须失败并输出候选诊断，而不是退回点击左树节点、普通文本或非数据行后报告成功。
- 扩展 `editable_table.fill_row` 结构化参照成功标准：对于会带出同一行派生字段的树表参照，不能只以目标单元格非空作为唯一成功信号；至少要保留可判断实际候选类型和选择态的诊断。
- 扩展字段级报告诊断，记录 `first_available` 实际选择的候选类型、候选文本摘要、是否来自右侧表格行、是否要求/具备选择态，便于区分手工等价选择和浅层回填。
- 不新增 DSL 语法，不改变 `tree + match` 精确选择、普通表格参照、普通下拉和普通文本/数字录入的既有语义。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `editable-table-cell-entry`: 修改 `editable_table.fill_row` 中结构化弹出参照 `tree + first_available` 的树表候选选择和成功诊断要求。

## Impact

- 运行时弹出参照候选选择逻辑，重点是 `_click_first_popup_reference_candidate`、树上下文应用后的候选根解析、选择态校验和确认/回填等待。
- 可编辑表格结构化参照字段结果和失败诊断。
- 回归测试需要覆盖 `物资入库` 的 `物资分类` 这类模板列为 `YDFInput`、运行时打开左树右表参照、`first_available` 必须选择右侧物资候选行并带出 `物资名称` 的场景。
- 真实验证需要使用当前源码运行原始问题用例，确认不再保存失败于 `物资名称不能为空`。
