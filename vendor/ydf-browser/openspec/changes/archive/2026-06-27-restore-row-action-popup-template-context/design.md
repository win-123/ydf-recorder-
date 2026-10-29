## Context

executor 在动作捕获到新的 `matchingTemplate` 后，会把当前 manifest 和 binding 压入 `_page_stack`，并记录动态模板来源。`popup_reference.select` 完成后已有自动恢复逻辑，但只允许来源为 `toolbar.click` 或 `action.click`。

本次真实链路是 `toolbar.click 分配` 进入包含 `物资信息`、`物资申请出库信息` 的分配页，再由 `table_row_action.click 选择库存` 直接打开参照模板。参照确认关闭后，当前动态模板来源仍是 `table_row_action.click`，现有入口保护直接返回 `False`，导致已关闭参照模板继续作为当前 manifest。

## Goals / Non-Goals

**Goals:**

- 在行级动作直接打开参照模板且参照关闭后，恢复上一层活动模板。
- 复用现有 action identity 和 manifest visibility 判断，避免无条件回栈。
- 让后续可编辑表格解析使用分配页真实表格名称。
- 保留自动恢复步骤数据和现有工具栏、通用动作恢复行为。

**Non-Goals:**

- 不改变 `editable_table.fill_row target.table` 语义或名称匹配规则。
- 不新增 DOM 表格标题推断或改写模板中的通用 `label=表格`。
- 不改变弹出参照的过滤、行匹配、确认和回填逻辑。

## Decisions

1. 将紧邻 `popup_reference.select` 的 `table_row_action.click` 纳入现有自动恢复判定。

   恢复函数检查上一层 manifest 是否重新可见、当前 manifest 的非共享稳定动作身份是否仍可见，并比较两层 visibility score。实现同时要求上一成功步骤就是 `table_row_action.click`，用于证明当前动态模板是该行级动作刚打开的参照模板；如果中间已经执行 `toolbar.click` 等步骤，则保留当前行级编辑表单。

   备选方案是在 `editable_table.fill_row` 发现表名不匹配时自动回栈。该方案会把错误恢复放到后续组件中，掩盖真正的上下文生命周期缺陷，因此不采用。

2. 不对所有 `table_row_action.click` 动态模板无条件恢复。

   行级 `编辑`、`详情` 也可能进入需要持续操作的动态表单。只有执行 `popup_reference.select` 后，且现有可见性与动作身份判断确认上一层重新成为活动面时才恢复；当前行级编辑表单仍可见时继续保留。

3. 保持现有报告字段。

   恢复成功继续记录 `restored_template` 和 `auto_restored_template: true`。无需新增诊断字段；真实报告可以直接证明第 7 步已恢复，后续第 8 步使用正确 manifest。

4. 共享动作身份不作为当前参照仍活跃的证据。

   YonDiF 不同动态模板可能复用 `btn-close`、`btn-save` 等 fieldid。参照关闭后，上一层的 `取消` 或 `暂存` 不能让已关闭参照模板误判为仍可见。恢复保护复用现有 `_manifest_visible_unshared_action_identity_matches`，只让当前模板独有的稳定动作阻止恢复。

## Risks / Trade-offs

- [Risk] 背景上一层残留可见元素可能诱发误恢复。→ Mitigation：继续使用当前 manifest 稳定动作身份和 visibility score 双重保护，并补充“行级编辑表单仍活跃时不恢复”回归。
- [Risk] 某些参照模板与上一层模板使用相同动作身份。→ Mitigation：沿用现有按 fieldid/key/rightflag 等身份匹配的保护，不退化为仅按按钮文本判断。
- [Risk] 真实用例后续可能暴露独立业务数据问题。→ Mitigation：验收至少要求原失败点越过，并按实际后续结果区分上下文修复与业务校验。
