## Why

真实用例中 `target.table: 调出方` 已经根据当前 manifest 解析为 `table_fieldid=table1`，但 runtime 在 DOM 中存在多个同 fieldid 候选时，可能让背景旧表格根凭 `selectableRows` 排序胜出。结果是已解析到正确 fieldid 后仍落到不可接收 pointer 事件的表格根，导致用户可见的一行数据被报告为 `当前可见有效行数=0`。

## What Changes

- 修复 `table_row_selection.select` 已解析出 `table_fieldid` 后的 DOM 根候选选择：只在该 fieldid 对应候选内决策，并优先当前前景、可见、包含可接收 pointer 事件业务行的表格根。
- 保持 fieldid 优先级规则：manifest 能把 `target.table` 解析到 fieldid 时，不按表名文本重新全局匹配其它表格根。
- 保持 WUI 表头/表体分裂 DOM 聚合、checkbox 优先、无 checkbox 行点击兜底和失败诊断的既有语义。
- 增加回归验证，覆盖同 fieldid 背景旧根有 `selectableRows`、前景真实根无 checkbox 但有可接收业务行时，必须点击前景业务行。
- 不改变 DSL 语法，不新增依赖，不扩大到其它组件定位语义。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `table-row-selection`: 明确并验证 `table_fieldid` 已解析成功时，同 fieldid DOM 候选必须优先前景可接收业务行根，不能让背景旧根或表名文本回退覆盖 fieldid 选择结果。

## Impact

- 影响代码：`ydf_browser/runtime.py` 的表格 fieldid 根候选解析、候选排序和按行号选择链路。
- 影响测试：`tests/test_runtime.py`，必要时补充 `tests/test_executor.py` 验证 executor 仍只传递 manifest 解析出的 `table_fieldid`。
- 影响规格：`openspec/specs/table-row-selection/spec.md` 的 delta spec。
- 不影响 DSL schema、命令行参数、登录链路、下载/导入链路或发布包结构。
