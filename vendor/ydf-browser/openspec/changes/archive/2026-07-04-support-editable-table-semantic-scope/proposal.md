## Why

`editable_table.fill_row` 当前只用可编辑表格 region 自身的 `label` 解析 `target.table`。在工资指标规则设置页面，用户能看到的表名 `指标挂接规则` 来自父卡片，真实表 region 的 `label` 却只是泛名 `表格`，导致写可见名称或运行时 `table_rule_table` 都在业务动作前失败。

## What Changes

- 扩展可编辑表格作用域解析：`target.table` SHALL 支持匹配表 region 的 `fieldid`、`runtime_fieldids`，以及唯一关联的父卡片或页签语义标题。
- 保持既有 `table: 表格` 兼容，但在多张泛名表并存时优先使用更稳定的语义标题或表身份。
- 改善表名不匹配错误，报告可用表的语义标题、region `fieldid` 和 runtime fieldid，避免只输出多个 `表格`。
- 不新增 DSL 字段，不引入新依赖。

## Capabilities

### New Capabilities

### Modified Capabilities
- `editable-table-cell-entry`: 可编辑表格录入时的 `target.table` 作用域解析增加父级语义标题和表身份匹配能力。

## Impact

- 影响 `ydf_browser/executor.py` 的可编辑表格作用域解析与诊断。
- 影响模板解析结果中已有的 `Region.parent_region_key`、`Region.runtime_fieldids` 使用方式，不改变数据模型。
- 增加聚焦单元测试覆盖父卡片标题、`fieldid`、runtime fieldid 和错误诊断。
- 需要用真实工资发放 YAML 验证最后一步可以按 `指标挂接规则` 或 `table_rule_table` 继续执行到目标单元格录入路径。
