## Context

当前 `table_row_selection.select` 支持 `target.match.conditions`，executor 会把完整 `match` 传给 runtime。runtime 进入带列匹配路径后，只提取第一个条件列作为 `column`，再把 `payload.match` 重建为 `{column, equals}` 传给 `_TABLE_ROW_VALUES_SCRIPT`。

`_TABLE_ROW_VALUES_SCRIPT` 已经有 `conditions.every(...)` 的 AND 匹配能力，但由于 Python 层丢掉了原始条件数组，真实页面会退化为首条件匹配。待分预算管理真实用例中，多行共享 `一级项目名称=财政一级项目ys06231632`，目标行还需要满足 `指标金额=888.00`，当前运行时会选中第一条同项目行。

## Goals / Non-Goals

**Goals:**

- 保留完整 `target.match.conditions`，让运行时按同一业务行的全部声明列执行 AND 匹配。
- 继续复用现有表格作用域、WUI header/body 聚合、列身份映射、树形表格展开和无 checkbox 行点击兜底。
- 用聚焦测试覆盖“首条件重复、完整条件在后续行命中”的误选回归，并用真实 DSL 证明修复。

**Non-Goals:**

- 不修改 DSL schema 或用户写法。
- 不新增表格专用分支，不把待分预算管理页面做成特例。
- 不重做表格绑定、列身份映射或报告结构。

## Decisions

- 在 runtime 内保留完整 `match` 作为行定位输入。相比在 executor 中预处理条件，runtime 已经拥有表格根、列身份和 DOM 行定位上下文，改动集中且不会扩散接口语义。
- 继续让 `_TABLE_ROW_VALUES_SCRIPT` 执行列级 AND 判断。相比新增 Python 侧 DOM 遍历，这能复用现有 header/body 分离、`data-index`/`fieldid` 等价和可见行筛选逻辑。
- 单条件路径保持兼容：`target.match.column` / `target.match.equals` 仍可走原有一列匹配；多条件只是在同一脚本调用里传入完整条件。
- 测试优先验证实际点击的业务行，而不是只验证步骤成功。绿色 step 不足以证明业务行正确，回归测试必须能在误选第一行时失败。

## Risks / Trade-offs

- 条件列横向滚动不可见时可能暴露既有列滚动不足的问题 → 先复用现有列可见和 header/body 聚合能力，真实 DSL 失败时再按证据处理列滚动。
- 复合条件中数值格式可能存在 `888.00` 与 `888` 的显示差异 → 保持现有字符串归一化策略，不在本 change 中引入金额格式推断。
- 成功报告仍主要证明根作用域和选择状态 → 本 change 聚焦修正实际选择行；如后续需要更强审计，再单独增加命中行摘要诊断。
