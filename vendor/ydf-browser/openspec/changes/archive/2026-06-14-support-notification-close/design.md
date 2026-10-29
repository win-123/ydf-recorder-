## Context

`ydf-browser` 目前把页面提示处理分成两层：点击类动作在执行前开启提示捕获，动作完成后把捕获到的 `data.notifications` 交给 executor；executor 发现 `error` 类型提示时，要求下一步必须紧接 `notification.assert`，否则把该点击动作判定为失败。这条保护能防止真实业务错误被误吞。

现有 `notification.assert` 只负责匹配最近一次动作捕获到的提示，成功后不改变页面状态。真实 YonDiF 页面中，成功和警告通常会自动关闭；错误提示可能以持久 `notification` 或 `modal-confirm` 形式留在页面上，需要用户主动点关闭、确定或类似按钮。预期错误断言后继续操作时，旧错误提示会遮挡后续动作，或者被下一次提示采集再次当成未处理错误。

本次设计需要保持既有“未预期 error 必须断言”的安全边界，同时提供一个可审计、可诊断的手工关闭表达。

## Goals / Non-Goals

**Goals:**

- 新增 `notification.close`，显式表达关闭当前可见、且与目标条件匹配的页面提示。
- 复用 `notification.assert` 的匹配字段：`type`、`contains/message_contains/text_contains`、`message`、`equals`。
- 关闭操作必须限定在匹配提示根节点内，不能全页面裸点 `关闭`、`确定` 或其他按钮。
- 支持常见 `.ant-*`、`.u-*`、`.wui-*` 的 message、notification 和 modal-confirm 结构。
- 关闭成功后刷新 executor 的最近提示缓存，避免已关闭错误影响后续点击动作。
- 补充 DSL 校验、runtime 诊断、单元测试、文档和真实 YAML 示例整理。

**Non-Goals:**

- 不改变 `notification.assert` 默认行为；断言仍然不自动关闭。
- 不移除 error notification 必须紧接 `notification.assert` 的安全保护。
- 不实现通用弹窗自动化或任意 DOM 点击能力；本变更只处理页面提示组件。
- 不要求自动关闭所有成功、警告或错误提示；是否关闭由 DSL 显式表达。
- 不解决业务错误本身，只让预期负向提示校验后能继续模拟真实手工操作。

## Decisions

1. 新增独立 `notification.close`，而不是给 `notification.assert` 默认加自动关闭。

   `assert` 和 `close` 是两个不同意图：前者是验证，后者是状态清理。默认自动关闭会改变大量既有用例行为，也可能吞掉用户想在后续步骤继续观察的提示。独立步骤让负向链路更清楚，也保留向后兼容。

2. `notification.close` 复用 `notification.assert` 的匹配字段，并增加可选 `label` / `button` 指定关闭按钮。

   常规写法应只需要：

   ```yaml
   - component: notification
     operation: close
     target:
       type: error
       contains: 请联系管理员
   ```

   如果某个 confirm 提示按钮不是默认候选，可使用 `label: 我知道了` 或 `button: 我知道了` 指定根内按钮。`label` 只在匹配提示根内生效，不能扩大到页面全局。

3. runtime 应先定位匹配提示根，再在根内关闭。

   通知扫描脚本需要返回足够的根节点信息，或关闭方法需要重新按相同选择器扫描并匹配文本。关闭候选优先级：

   - notification/message 根内显式 close icon 或关闭按钮，例如 `.ant-notification-notice-close`、`.wui-message-notice-close`、`.wui-notification-close-x`、`[aria-label=close]`。
   - modal-confirm 根内的指定 `label`。
   - modal-confirm 根内默认按钮文本：`关闭`、`确定`、`确认`、`我知道了`、`OK`。

   关闭脚本只负责在匹配根节点内部定位并标记关闭入口，实际点击使用 Playwright locator click，避免页面上下文 `element.click()` 对部分 WUI 持久提示不生效。找不到关闭入口时步骤失败并输出匹配提示文本和候选诊断。

4. executor 在 `notification.close` 后刷新 `_last_notifications`。

   关闭成功后，executor 应重新调用 `collect_notifications` 或让 runtime 返回关闭后的剩余提示，并把 `_last_notifications` 更新为剩余可见提示。这样后续 `toolbar.click` 的错误保护不会继续看到已处理的旧错误。步骤结果应记录 `closed_notification`、`remaining_notifications` 和 `close_action`。

5. `notification.close` 不替代 `dialog.confirm`。

   `dialog.confirm` 表示业务弹窗按钮点击，可能触发模板切换、下载、保存等业务动作；`notification.close` 只用于提示层清理。即使错误提示渲染为 modal-confirm，也必须按提示文本匹配后在该提示根内关闭，不能把它当作普通业务弹窗。

## Risks / Trade-offs

- [Risk] 不同 UI 框架关闭按钮 DOM 差异较大。→ Mitigation: 关闭候选覆盖 Ant/U/WUI 常见 close icon、aria-label、title 和 confirm 按钮文本，并在失败时输出提示根文本和候选诊断。
- [Risk] 全页面裸点 `确定` 可能误触业务弹窗。→ Mitigation: runtime 必须先匹配通知根，所有关闭候选都限定在该根内；找不到根内按钮时失败。
- [Risk] 已关闭提示仍留在 observer 缓冲区，导致 `_last_notifications` 污染。→ Mitigation: 关闭后重新扫描当前可见提示，并让 executor 用剩余可见提示覆盖缓存；必要时排除本次已关闭的匹配提示。
- [Risk] 某些错误提示没有可见关闭入口，只能等待或需要业务按钮。→ Mitigation: `notification.close` 明确失败并保留诊断，不伪装成功；用例作者再改用合适的业务步骤。
- [Risk] `type` 推断依赖 class 文本，部分 modal-confirm class 不带 error。→ Mitigation: 匹配时继续支持不写 `type`，推荐负向用例同时写 `contains`；如果写了 `type: error`，实现应尽量从 error icon/class 推断 confirm 类型。

## Migration Plan

- 这是向后兼容扩展；已有 `notification.assert` 用例不需要迁移。
- 对需要在预期错误后继续执行的用例，在 `notification.assert` 后显式追加 `notification.close`。
- 文档中补充负向链路推荐写法：点击动作 -> `notification.assert` -> `notification.close` -> 后续业务步骤。
