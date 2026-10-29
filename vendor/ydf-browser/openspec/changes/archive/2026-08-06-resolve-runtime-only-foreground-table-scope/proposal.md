## Why

动态模板弹窗可能已经渲染出可见、可交互的前景表格，但当前 manifest 尚未声明对应 region。现有表格作用域解析只扫描 manifest region，导致 DSL 即使给出该表格的精确 fieldid，也会在动作前被误判为名称未匹配。

## What Changes

- 当 `target.table` 给出 manifest 未声明的精确 fieldid 时，增加一次受限的运行时 DOM 探测。
- 仅在该 fieldid 对应唯一、可见、可交互的前景表格且包含全部必需列时解析成功。
- 保留现有背景拒绝、缺列、歧义和未找到语义；不增加中文表名或模糊名称猜测。
- 增加来自 `ai-observe-7` 失败形态的回归测试，并用真实 DSL 验证动态模板弹窗。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `table-scope-resolution`: 补充 manifest 未声明但运行时 DOM 已存在的精确前景表格 fieldid 解析契约。

## Impact

- 影响共享表格作用域解析入口 `ydf_browser/table_scope.py` 及其聚焦测试。
- `editable_table.*`、`table.*` 等复用该入口的动作共同获得修复，不增加页面专用分支。
- 不新增依赖，不改变 DSL schema。
