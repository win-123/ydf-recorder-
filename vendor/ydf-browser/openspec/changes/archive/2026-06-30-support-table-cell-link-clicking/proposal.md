## Why

YonDiF 列表页中有些表格列使用 `link` 组件渲染，业务入口不是工具栏按钮，也不是 hover 后出现的行级按钮。当前 DSL 只能用 `toolbar.click` 或 `table_row_action.click` 间接表达，容易误点同名工具栏动作或全页面文本，无法稳定点击目标行目标列中的超链接。

## What Changes

- 新增 `table.click_cell_link` DSL 操作，用于在表格目标行的指定列内点击真实可点击链接。
- 复用现有表格作用域和行定位语义，包括 `target.table`、`target.match`、`target.row_number`、`target.first_available`。
- 点击后纳入现有点击类动作处理，支持通知捕获、动态模板识别和步骤结果诊断。
- 明确失败边界：找不到目标行、找不到目标列、目标单元格不是可点击链接时必须失败。

## Capabilities

### New Capabilities
- `table-cell-link-clicking`: 支持按表格行和列定位并点击单元格内超链接。

### Modified Capabilities

无。

## Impact

- 影响 DSL 校验与示例：新增 `table.click_cell_link` 的目标字段校验和错误提示。
- 影响 executor：新增表格单元格链接点击分发，复用表格作用域解析、点击后动态模板切换和通知捕获。
- 影响 runtime：新增按行列定位单元格并点击链接的运行时能力。
- 需要补充单元测试和真实用例验证，重点覆盖 `盘点任务填报` 未盘点页签中 `任务编码` 链接点击。
