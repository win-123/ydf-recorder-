## Why

真实用例 `/Users/ken/temp/ydf-browser-问题反馈/实物管理-易耗品物资-入库填报-新增-0001 2.yaml` 在 `editable_table.fill_row` 录入 `物资分类` 时失败：DSL 使用 `tree.label: A05040101 复印纸` 限定左树，再用 `match.column: 物资编码` 精确选择右侧候选 `A050401010000000001`。诊断截图显示该候选真实存在于右侧表格第 13 行，但运行时 `match` 路径没有识别到右侧候选表格，报告 `headerCount=0`、`strictRowCount=0`。

仓库样例 `examples/material_stockin_material_category_popup_reference.yaml` 使用同一页面、同一字段、同一左树节点的 `first_available: true` 已能通过，说明登录、菜单、弹窗打开和基础数据并非根因；缺口集中在树表弹窗应用左树上下文后按右侧表格列精确匹配候选的能力。

## What Changes

- 扩展 `editable_table.fill_row` 结构化弹出参照录入能力：当字段值包含 `tree` 和 `match` 时，运行时必须在应用参照内树上下文后，识别右侧候选表格并按指定列和值选择目标行。
- 覆盖真实页面使用的 W table 渲染形态，避免 `first_available` 能识别候选而 `match.column` 路径看不到同一候选表格。
- 失败诊断必须保留精确匹配上下文，包括目标列、目标值、候选表头、候选行摘要和诊断截图，便于区分“数据不存在”和“候选表格未被识别”。
- 不新增 DSL 语法，不改变 `tree + first_available`、普通表格参照、普通文本/数字录入的既有语义。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `editable-table-cell-entry`: 可编辑表格结构化弹出参照目标需要支持 `tree + match` 在树表弹窗中的精确右表候选选择。

## Impact

- 运行时弹出参照候选表格识别与点击逻辑，重点是 `_select_popup_reference`、`_click_popup_reference_table_row` 和候选表格调试采集。
- 可编辑表格结构化参照字段结果与失败诊断。
- 回归测试需要覆盖 `物资入库` 的 `物资分类` 这类模板列为 `YDFInput`、运行时弹出左树右表参照的场景。
- 真实验证需要使用当前源码运行原始失败用例，确认不再失败于 `物资分类 tree + match(物资编码)`。
