## 1. DSL 校验

- [x] 1.1 在 `ydf_browser/dsl.py` 中注册 `notification.close` 组件操作，并允许 `type`、`contains`、`message_contains`、`text_contains`、`message`、`equals`、`label`、`button` target 字段。
- [x] 1.2 为 `notification.close` 增加业务执行前校验，要求至少提供一个提示匹配条件，避免无条件关闭任意提示。
- [x] 1.3 保持 `notification.assert` 的既有 schema 和行为不变，不增加默认自动关闭。
- [x] 1.4 补充 `tests/test_dsl.py`，覆盖接受 `notification.close`、接受显式 `label/button`、拒绝空关闭目标、拒绝未知 target 字段。

## 2. Executor 分流与状态刷新

- [x] 2.1 在 `WorkflowExecutor` 中新增 `notification.close` 分支，复用 `notification.assert` 的匹配条件解析和错误信息风格。
- [x] 2.2 调用 runtime 的通知关闭方法时传递 `type`、文本匹配条件和可选关闭按钮标签，并把返回的关闭结果写入步骤 `data`。
- [x] 2.3 `notification.close` 成功后刷新 `_last_notifications` 为当前剩余可见提示，确保已关闭错误不再影响后续点击动作。
- [x] 2.4 补充 executor 单元测试，覆盖预期错误 `toolbar.click -> notification.assert -> notification.close -> toolbar.click` 能继续执行。
- [x] 2.5 补充 executor 单元测试，覆盖关闭一条提示后保留其他 `remaining_notifications` 并刷新缓存。

## 3. Runtime 通知关闭

- [x] 3.1 在 Playwright runtime 增加 `close_notification(...)`，按通知根节点重新扫描可见 `.ant/.u/.wui` message、notification、modal-confirm 和 `[role=alert]`。
- [x] 3.2 实现与 `notification.assert` 一致的类型和文本匹配逻辑，确保只定位满足 target 条件的提示根。
- [x] 3.3 在匹配根内优先点击 close icon / close control，支持常见 `aria-label`、`title`、close class 和按钮形态。
- [x] 3.4 对 modal-confirm 形态支持 `target.label` / `target.button`，以及默认候选 `关闭`、`确定`、`确认`、`我知道了`、`OK`，并限定在匹配根内点击。
- [x] 3.5 点击关闭入口后等待该提示根消失或同一 `type/message` 不再可见；仍可见时失败并保留诊断。
- [x] 3.6 找不到匹配提示或找不到关闭入口时抛出明确错误，错误信息包含期望条件、当前可见提示摘要和关闭候选诊断。
- [x] 3.7 补充 runtime 单元测试，覆盖普通 notification close icon、modal-confirm 确认按钮、全局同名按钮不误点、无匹配提示失败、无关闭入口失败、关闭后仍可见失败。

## 4. 文档与示例

- [x] 4.1 更新 `README.md` 的组件列表和提示断言说明，加入 `notification.close` 简短说明。
- [x] 4.2 更新 `docs/action-capability-test-plan.md`，补充负向提示断言后关闭的验证点和 YAML 模板。
- [x] 4.3 更新 `AGENTS.md`，记录错误提示需要显式 `notification.close` 清理，通知/警告自动关闭不等于错误提示自动关闭。
- [x] 4.4 如存在 `skills/gov-ydfdev-browser/references/dsl-reference.md`，补充 `notification.close` 语法和推荐链路。
- [x] 4.5 整理 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-项目预算-YDF-81116-0001.yaml` 或新增 repo 内示例，展示 `预算调整` 错误断言后关闭再继续 `选择项目预算`。

## 5. 验证

- [x] 5.1 运行聚焦测试：`tests/test_dsl.py`、`tests/test_executor.py`、`tests/test_runtime.py` 中新增和相关用例。
- [x] 5.2 运行 `openspec validate support-notification-close --strict`。
- [x] 5.3 如环境可用，使用 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-项目预算-YDF-81116-0001.yaml` 或整理后的示例真实验证错误提示断言、关闭和后续步骤继续执行；已用当前源码目录执行 `examples/project_budget_notification_close.yaml`，真实报告 `reports/20260614-113746-c94682f3/report.json`，结果 `success=true`。
- [x] 5.4 运行 `git diff --check`，确认 OpenSpec artifacts 和实现文件没有空白错误。
