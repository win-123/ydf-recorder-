## Context

ydf-browser 在执行 YonDiF 单据页时会维护当前 manifest、当前 binding 以及上一层模板栈。行级 `编辑`、工具栏 `新增`、弹窗按钮等动作可能触发动态模板响应，executor 会把当前模板入栈并切换到新模板；后续 `保存`、`取消`、`确定` 等动作又可能需要恢复上一层列表模板。

当前 `dialog.confirm` 的自动恢复判断较宽：只要动态模板来源是 `table_row_action.click` 或 `editable_table.add_row`，且上一层列表 manifest 在当前 DOM 中有可见度，就会恢复上一层。生成支付单用例中，行级 `编辑` 进入编辑页后，`选择付款账户` 打开参照并触发一个业务确认框；确认框关闭后页面仍停留在编辑页，但上一层列表的一些元素仍可被采集到，于是 executor 误恢复到列表页 manifest，后续 `保存` 无法绑定。

## Goals / Non-Goals

**Goals:**

- 让 `dialog.confirm` 只在真实返回上一层页面时恢复上一层 manifest。
- 保留弹出参照后业务确认框关闭但编辑页仍可操作的动态模板上下文。
- 保持已有保存、取消、确认后确实回列表的自动恢复体验。
- 通过单元回归和真实 YAML 复现验证该路径。

**Non-Goals:**

- 不新增 DSL 语法或要求用例显式写 `restore_previous`。
- 不改变 popup_reference 的选择语义、过滤语义或确认按钮选择器。
- 不解决业务数据导致的后续保存失败或生成支付单业务校验失败。

## Decisions

1. 在 `dialog.confirm` 自动恢复前加入当前模板稳定动作保护。

   当前动态模板如果仍然有可见、身份匹配的稳定表单动作，例如 `保存`、`提交`、`取消`、`确定`、`确认`，executor SHALL 认为当前编辑/表单模板仍处于前景，不自动恢复上一层。这个判断与已有 form popup reference 恢复逻辑一致，避免只凭上一层列表可见度做决定。

   备选方案是删除 `dialog.confirm` 自动恢复，但会破坏行级弹窗确认后确实回列表的既有行为；因此选择收窄判断而不是移除功能。

2. 区分“业务确认框关闭”和“动态模板关闭”。

   `dialog.confirm` 点击的是前景确认框按钮，不等价于关闭当前动态模板。恢复上一层前需要确认当前动态模板的核心动作不再可见，或上一层 manifest 的可见度明显超过当前 manifest。这样能够覆盖付款账户确认这类中间业务弹窗。

   备选方案是在用例中给 `dialog.confirm` 增加参数禁止恢复，但这会把运行时状态机细节泄漏给 DSL 使用者，也不能修复同类页面。

3. 保留真实返回列表的自动恢复路径。

   保存、取消、确认后如果当前动态模板的稳定动作已消失，并且上一层列表 manifest 可见，仍自动恢复上一层 manifest。实现时应复用现有 `_manifest_has_visible_action_identity`、`_manifest_visibility_score` 等辅助函数，避免新增一套不一致的 DOM 判断。

## Risks / Trade-offs

- [Risk] 当前模板稳定动作因 DOM 延迟短暂不可见，仍可能误恢复上一层。→ Mitigation：确认后等待现有动作稳定窗口，并用可见度评分作为辅助，而不是仅判断单个按钮。
- [Risk] 某些真实返回列表场景中背景仍残留表单动作副本，导致不恢复。→ Mitigation：回归测试覆盖保存/取消返回列表路径；必要时按 action identity 和 pointer 可达性过滤稳定动作。
- [Risk] 真实用例后续可能因业务数据失败。→ Mitigation：本 change 的验收边界是 `保存` 动作能够在编辑页 manifest 下执行；后续业务校验失败单独判断。
