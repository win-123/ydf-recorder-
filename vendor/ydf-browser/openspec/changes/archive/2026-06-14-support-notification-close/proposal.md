## Why

当前 `notification.assert` 只能断言最近一次动作捕获到的页面提示，但无法表达“这个预期错误已经校验完，需要主动关闭后继续执行”。真实 YonDiF 页面里通知和警告通常会自动消失，而错误提示可能以持久 notification 或 modal-confirm 形态停留在页面上，导致后续步骤被旧错误遮挡或被执行器误判为新的未处理错误。

例如 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-项目预算-YDF-81116-0001.yaml` 中，点击 `预算调整` 后预期出现 `请联系管理员` 错误；断言成功后如果不关闭该错误提示，下一步点击 `选择项目预算` 会继续受到旧错误提示影响，流程无法表达真实手工操作。

## What Changes

- 新增 `notification.close` DSL 操作，用于按 `type`、`contains/message_contains/text_contains`、`message` 或 `equals` 定位并关闭当前可见页面提示。
- `notification.close` 必须只关闭匹配到的提示根节点，不能退回全页面裸点 `关闭`、`确定` 或其他按钮。
- 关闭语义覆盖常见 YonDiF/Ant/U/WUI message、notification 和 modal-confirm 形态：普通通知优先点击关闭图标，confirm 类错误提示可点击根内 `关闭`、`确定`、`我知道了`、`OK` 等可配置确认按钮。
- `notification.assert` 继续保持只断言、不自动关闭，避免吞掉未预期错误；用例需要继续执行时显式追加 `notification.close`。
- 关闭成功后执行器应刷新最近提示缓存，避免已关闭的旧错误继续影响后续 `toolbar.click` / `action.click` / `dialog.click` / `tab.click` 错误判定。
- 补充 DSL 校验、运行时诊断、文档、示例和回归测试，覆盖预期错误断言后关闭并继续执行的链路。

## Capabilities

### New Capabilities

- `notification-handling`: 描述页面提示捕获、断言、未处理错误保护，以及预期持久提示的显式关闭语义。

### Modified Capabilities

- 无。

## Impact

- 影响 DSL schema、executor 的 notification 分流和错误缓存处理、Playwright runtime 的通知关闭定位、DSL 文档、能力测试计划和相关单元测试。
- 主要涉及 `ydf_browser/dsl.py`、`ydf_browser/executor.py`、`ydf_browser/runtime.py`、`docs/action-capability-test-plan.md`、`README.md`、`AGENTS.md` 和 `tests/`。
- 不引入新外部依赖，不改变 `notification.assert` 的默认行为，不改变未预期 error notification 必须紧接 `notification.assert` 才能继续的安全保护。
