## Context

`editable_table.add_row` 目前由 executor 先把 `target.table` 解析为模板表格身份，再把 `table`、`table_fieldid` 和 `table_columns` 传给 runtime。问题用例中 `target.table=需求清单` 已解析到 `table_fieldid=cgbd_table`，说明 DSL 表名和模板解析不是根因。

运行时脚本点击 `+ 新增` 后，会用 `validationRootFor(chosen.root)` 向父级容器寻找行数较多的 root，再用该 root 的 `rowState` 判断新增是否成功。采购需求编制页面在同一表单区域内还存在采购要求等其他明细行，导致验证 root 吸入了非目标表格的既有数据行，`需求清单` 自身仍为空却被误判为新增成功。

## Goals / Non-Goals

**Goals:**
- `editable_table.add_row` 的点击候选和新增后验证都限定到目标表格身份、目标 fieldid 或等价目标 root。
- 点击后如果目标表格仍为空态或没有真实可编辑数据行，当前 `add_row` 步骤直接失败并输出诊断。
- 报告中的 `row_state` 能代表目标表格，而不是外层容器或相邻表格。

**Non-Goals:**
- 不改变 DSL 语法，不新增 `wait`、坐标或页面专用参数。
- 不改变 `editable_table.fill_row` 的参照列录入策略。
- 不处理采购需求页面的业务数据、必填校验或后续保存提交规则。

## Decisions

1. 让目标表格 root 成为新增验证的唯一事实源。

   runtime 已经接收 `tableFieldid` 和 `tableColumns`，应在脚本中先尝试把候选按钮绑定到包含该 fieldid 或目标列身份的表格 root。点击后验证只允许在这个目标 root 或其明确等价 root 内计算 `rowState`，不能继续向上选择包含更多行的祖先容器。

   选择原因：问题不是没传身份，而是验证阶段放大了作用域。修在 runtime 的共享脚本里，比在 executor 或单个 YAML 上补特例更小。

2. 失败时优先报告“新增行未生效”。

   当点击入口存在但目标表格仍为空，错误应指向 `editable_table.add_row` 未产生目标数据行，并带上 `target.table`、`table_fieldid`、候选 root 摘要、目标 `rowState` 和截图。这样用户可以区分按钮未找到、表名不匹配、点击无效和页面业务阻止新增。

   备选方案是在后续 `fill_row` 找不到可编辑行时回溯修正错误归因。这个方案更绕，而且仍会生成误导性的成功步骤。

3. 单测覆盖 root 收窄，真实 DSL 验证覆盖页面行为。

   单测应构造一个目标空表和一个相邻已有数据表，验证 `add_row` 不会把相邻数据行当作目标新增成功。真实验证仍使用本次问题 YAML，确认修复前失败归因在 `add_row`，修复后至少能证明 `需求清单` 出现可编辑数据行并进入后续录入。

## Risks / Trade-offs

- [Risk] 某些页面的新增按钮不在目标 table root 内，而在分组标题或区域工具栏中。→ Mitigation: 候选点击仍可使用现有 table label、fieldid 和列身份评分；收紧的是点击后的验证 root，不是完全拒绝区域外按钮。
- [Risk] 部分表格新增后需要更久才渲染行。→ Mitigation: 保持现有短等待，并在必要时只增加针对目标 root 的轻量轮询，避免全页面长等待。
- [Risk] 目标表格 DOM 缺少 fieldid 属性。→ Mitigation: 保留 `tableColumns` 和语义标题作为等价 root 识别兜底；无法唯一识别时失败并输出候选诊断。
