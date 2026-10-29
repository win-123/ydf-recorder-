## Why

`table_row_selection.select target.match.conditions` 已经被规格定义为 AND 条件，但当前运行时在带列匹配路径中只把第一个条件传给行定位脚本。真实用例中多条记录共享同一个 `一级项目名称` 时，步骤会选中第一条同项目行，而不是同时满足 `指标金额=888.00` 的目标行。

## What Changes

- 修复复合条件行选择路径，确保运行时按全部 `target.match.conditions` 定位同一业务行后再点击该行选择控件。
- 保持单条件 `target.match.column` / `target.match.equals`、表格作用域、WUI 表头/表体身份映射和无 checkbox 行点击兜底的既有行为。
- 增加回归验证，覆盖第一条可见行只满足部分条件、后续行满足全部条件时必须选择后续目标行。
- 不改变 DSL 语法，不新增依赖，不扩大到其它组件选择语义。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `table-row-selection`: 明确并验证 `target.match.conditions` 在运行时行定位中必须完整保留为 AND 条件，不能退化为首条件匹配。

## Impact

- 影响代码：`ydf_browser/runtime.py` 的表格行复合条件定位链路，必要时补充 executor/runtime 层诊断。
- 影响测试：`tests/test_runtime.py`，必要时补充 `tests/test_executor.py` 对参数透传的窄覆盖。
- 影响规格：`openspec/specs/table-row-selection/spec.md` 的 delta spec。
- 不影响 DSL schema、命令行参数、登录链路、下载/导入链路或发布包结构。
