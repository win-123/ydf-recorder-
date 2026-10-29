## Context

当前 executor 通过 `current_manifest` 和 `_page_stack` 维护动态模板上下文。`toolbar.click 保存/提交` 已复用 `_should_auto_restore_previous_template_after_save()` 判断是否自动恢复上一层模板，但 `dialog.click` 只有 `确定/确认` 会进入自动恢复判断。

本次失败链路中，`toolbar.click 开具发票` 捕获了发票动态弹窗；`dialog.click 保存` 关闭该弹窗后未恢复到项目认领表单，导致后续项目认领主页面 `toolbar.click 保存` 只恢复到项目认领表单，而不是列表模板。页面已经返回列表，当前 manifest 却仍停在表单，最终 `toolbar.click 提交` 被元数据门禁拦截。

## Goals / Non-Goals

**Goals:**
- 让 `dialog.click 保存/提交` 关闭动态弹窗后复用保存后自动恢复逻辑。
- 保持错误通知时不恢复、当前表单仍可见时不恢复的既有保护。
- 用最小 executor 单测覆盖多层动态模板栈的恢复顺序。

**Non-Goals:**
- 不新增 runtime-only toolbar fallback。
- 不改变 `toolbar.click`、`action.click`、`dialog.confirm` 的既有语义。
- 不放宽 `table_row_selection.select` 的表格名解析。修复模板上下文后暴露出的表格名不匹配应继续作为 DSL 诊断返回。
- 不修改 DSL schema。

## Decisions

- 复用 `_should_auto_restore_previous_template_after_save()`，而不是新增一套 `dialog.click` 专用判断。该函数已经处理错误通知、当前稳定动作仍可见、上一层模板可见性和主表格恢复规则。
- 只在 `dialog.click` 的目标 label 为 `保存` 或 `提交` 时进入该判断。`确定/确认` 继续走现有 dialog-confirm 恢复逻辑，避免扩大行为面。
- 回归测试模拟三层栈：列表模板 -> 动态表单 -> 动态弹窗。弹窗保存后应恢复表单，表单保存后再恢复列表，最后列表页 `提交` 能解析。

## Risks / Trade-offs

- [Risk] 某些业务弹窗点击 `保存` 后仍停留在弹窗内。 -> Mitigation: 复用现有当前模板稳定动作/字段仍可见保护，不因背景元素可见就恢复。
- [Risk] 错误通知下恢复会隐藏业务校验信息。 -> Mitigation: 复用 `_has_error_notification` 保护。
- [Risk] 修复模板上下文后，旧 DSL 可能暴露新的表格名不匹配。 -> Mitigation: 保留严格诊断，不在本 change 中兼容错误模板上下文下形成的表格名。
