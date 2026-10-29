## Context

`ydf-browser` 使用 `current_manifest` 和 `_page_stack` 维护 YonDiF 动态模板上下文。现有实现已经覆盖保存/提交关闭动态模板后的自动恢复，也覆盖部分 `dialog.confirm` 场景，但 `dialog.confirm` 的自动恢复只面向 `editable_table.add_row` 和 `table_row_action.click` 打开的动态模板。

本次真实用例的路径不同：列表页 `toolbar.click 设置经费管理员` 打开动态弹窗模板，`form.fill 经费管理员` 后执行 `dialog.confirm 确认`，页面返回列表并提示 `更新成功！`，但 executor 仍停留在弹窗 manifest，导致下一步 `query.search 项目名称` 找不到列表查询字段。

## Goals / Non-Goals

**Goals:**

- `dialog.confirm` 成功关闭由 `toolbar.click` 打开的动态模板并返回列表时，自动恢复上一层模板。
- 保留错误通知保护，业务失败时继续停留在当前动态模板。
- 保留当前动态表单保护，确认后动态表单仍可见且可操作时不得误恢复。
- 后续 `query.search`、表格操作、工具栏操作都应使用恢复后的列表模板，不要求 DSL 显式写 `restore_previous`。

**Non-Goals:**

- 不新增 DSL 配置项。
- 不改变显式 `restore_previous` 的含义。
- 不做通用浏览器历史或路由恢复，只处理已有动态模板栈。

## Decisions

1. 复用现有恢复判定，不引入新的恢复模型。

   `_should_auto_restore_previous_template_after_confirm()` 已按确认动作、错误通知、上一层主表格、当前/上一层可见性做判断。实现阶段优先复用或收敛这类逻辑，而不是为 `设置经费管理员` 写页面特例。

2. 扩大 `dialog.confirm` 自动恢复适用上下文。

   现有 `_should_auto_restore_previous_template_after_dialog_confirm()` 只允许 `editable_table.add_row` 和 `table_row_action.click`，本次应允许 `toolbar.click` 打开的动态模板在满足同样可见性证据时恢复。

3. 恢复发生在 `dialog.confirm` 步骤内。

   第 15 步失败说明只在表格步骤前兜底不够；`query.search` 也需要正确上下文。确认步骤内恢复能让后续所有组件步骤共享同一结果。

4. 报告继续暴露恢复证据。

   自动恢复时继续输出 `restored_template` 和 `auto_restored_template: true`；未恢复时保持现有报告形态，便于通过真实报告判断当前模板是否被保留。

## Risks / Trade-offs

- 误恢复到背景列表 -> 通过“当前动态模板仍有稳定动作/字段可见则不恢复”降低风险。
- 确认后返回较慢 -> 复用现有短等待和运行时元素重采集，不引入固定长等待。
- 同名 `确定/确认` 按钮来源复杂 -> 只在已有 `_page_stack`、无错误通知、上一层模板可见的条件下恢复。
