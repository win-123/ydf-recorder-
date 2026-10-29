## Context

当前 `table_row_selection.select` 已支持 `target.first_available`，但 executor 会把它转换为 `row_number: 1`，runtime 的行号选择路径只统计带 checkbox 或等效选择控件的可见行。真实页面 `单位收入管理>>到账款项发布>>到账款项发布` 中，点击 `发布` 后弹窗里的 `dzkxxx_table` 展示一条到账款项业务行，但该表没有 checkbox；后续 `指定部门` 确认依赖这条业务行被选中，否则页面提示 `请选择一条到账款项数据！`。

同一项目里，按 `target.match.column + equals` 找到业务行后，已经允许在目标表格作用域内无选择控件时点击该业务行。这个 change 补齐 `first_available` 与已存在行匹配语义之间的不一致。

## Goals / Non-Goals

**Goals:**
- 让 `table_row_selection.select target.first_available` 表达“选择目标表格第一条有效业务行”，而不是隐含“第一条可勾选行”。
- 有 checkbox 或等效选择控件时继续优先点击选择控件。
- 无选择控件时，只在已解析的目标表格作用域内点击第一条有效业务行。
- 保留清晰诊断，能区分无有效业务行、无表格作用域、点击行后业务未选中等问题。

**Non-Goals:**
- 不新增 DSL 字段。
- 不改变 `target.select_all` 的表头 checkbox 语义。
- 不承诺跨分页、虚拟滚动之外的不可见行选择。
- 不把表头、小计/合计行、`暂无数据` 占位行当作 first available。

## Decisions

1. 复用现有 `first_available` 写法，不增加 `click_row_when_no_checkbox` 之类开关。

   原因：用户写 `first_available` 的业务意图是接受第一条有效候选。把“必须有 checkbox”暴露成额外配置只会把内部 DOM 约束推给用例作者。

2. 在 runtime 的行号选择路径补齐无选择控件兜底，而不是在 executor 层把 `first_available` 改写成临时 `match`。

   原因：当前失败发生在 `select_table_row_by_index()` 对第 1 行的解释上。把兜底放在 `_click_row_checkbox_by_index()` 这类共享行号路径里，可以同时覆盖显式 `row_number` 在指定表格无 checkbox 时的相同业务场景；但 DSL 校验和多表格歧义规则仍由 executor 维持。

3. 只点击有效业务行。

   原因：发布弹窗同时有表头、小计行和 `暂无数据` 占位区域。实现应复用或对齐 `_row_looks_like_table_data_row()`，跳过 header/footer/summary/empty 行，避免 first available 选择到非业务行。

4. 成功后保留现有步骤数据结构。

   原因：`table_row_selection.select` 成功结果已经包含 `row_numbers`、`table`、`table_fieldid`。本 change 不需要新增用户可依赖字段；如果实现需要调试，可在失败信息或已有诊断里补充行文本、表格根摘要。

## Risks / Trade-offs

- [Risk] 某些表格点击普通行只改变视觉高亮，不触发业务选中。→ Mitigation: 用真实 `到账款项发布` 截断流程验证到 `zdbm_btn_modal_ok` 后生成 `发布明细`，而不是只看步骤成功。
- [Risk] 无 `target.table` 时页面存在多张表格，点击第一条行可能误选。→ Mitigation: 保持现有多表格歧义检测；无明确唯一表格作用域时不做宽泛全页面点击。
- [Risk] 行号路径兜底可能影响过去期望“无 checkbox 即失败”的用例。→ Mitigation: 只在有效业务行存在且处于已解析表格作用域内时点击；失败诊断仍明确表格、行号和选择器统计。
