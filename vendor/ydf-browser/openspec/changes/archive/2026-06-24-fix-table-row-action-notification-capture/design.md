## Context

executor 目前把 `toolbar.click`、`action.click`、`dialog.click`、`tab.click` 这类点击动作包在页面提示捕获窗口内：点击前调用 runtime 的通知 observer，点击后收集提示并写入步骤结果和 `_last_notifications`。`notification.assert` 优先匹配这份最近提示缓存，因此可以断言已经自动消失的短 toast。

`table_row_action.click` 走的是另一条执行路径。它会先 hover 数据行，再点击行级按钮，并等待可能出现的动态模板；但它没有在点击前启动通知捕获，也没有把点击后的提示写回 `_last_notifications`。真实页面里 `生成支付单` 行级按钮会短暂弹出 `操作成功`，探针证明提示存在；原始 DSL 失败是因为等待结束后 toast 已消失，后续 `notification.assert` 只能现扫 DOM 得到空列表。

## Goals / Non-Goals

**Goals:**

- 让 `table_row_action.click` 的页面提示捕获行为与其他点击动作一致。
- 让紧随行级动作的 `notification.assert` 能匹配短暂出现后自动消失的成功或错误提示。
- 让未处理错误提示保护覆盖行级按钮点击。
- 保持现有行级按钮定位、hover、动态模板等待和报告字段语义。

**Non-Goals:**

- 不新增 DSL 字段或新的组件操作。
- 不改变 `notification.assert` 的匹配规则、等待窗口或关闭语义。
- 不调整 `toolbar.click`、`action.click`、`dialog.click`、`tab.click` 的既有行为。
- 不解决具体业务数据是否允许生成支付单的问题；本 change 只修复提示捕获缺口。

## Decisions

1. 在 `table_row_action.click` 点击前启动通知捕获。

   复用 executor 已有 `_begin_notification_capture()` / `_collect_notifications()`，在实际点击行级按钮前启动捕获，在动态模板等待和切换判断后收集提示。这样覆盖短 toast，同时避免新增 runtime API。

2. 行级动作步骤结果写入 `notifications` 并刷新 `_last_notifications`。

   `notification.assert` 已经优先读取 `_last_notifications`，因此最小实现是让行级点击和其他点击动作产出同样的数据形态。步骤结果中只有捕获到提示时才附加 `data.notifications`，保持报告简洁。

3. 将 `table_row_action.click` 纳入未处理错误提示保护集合。

   行级按钮同样会触发业务错误。如果下一步不是 `notification.assert`，executor MUST 把未处理错误提示视为当前行级动作失败；如果下一步紧接 `notification.assert`，则保留当前动作成功，让断言步骤验证该预期错误。

4. 不改变行级动作定位策略。

   当前问题不是点错按钮：真实探针在点击行级 `生成支付单` 后捕获到 `操作成功`。因此 change 不碰 `_resolve_visible_row_action()`、表格作用域判断或 hover 行逻辑。

## Risks / Trade-offs

- [Risk] 行级动作点击后同时触发动态模板和提示，收集提示时机过早可能遗漏。→ Mitigation: 保持现有动态模板等待后再收集，让 observer 缓冲覆盖等待期间出现的短提示。
- [Risk] 行级动作失败提示被新保护拦截，改变少数旧用例结果。→ Mitigation: 这与既有点击动作安全边界一致；预期错误应紧接 `notification.assert`。
- [Risk] 单元测试只用 fixture 捕获缓存，真实页面仍可能有时序差异。→ Mitigation: implementation 阶段必须跑原始真实 YAML，确认最后一步 `notification.assert` 通过。
