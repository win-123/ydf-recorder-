## Why

真实 DSL 的首个菜单步骤出现登录框，关闭窗口后报 `Page.reload: Target page, context or browser has been closed`。已复现 API 身份与业务上下文均有效、工作台首页却返回登录页的部分认证失效；现有准备流程在上下文无需切换时未检查工作台入口。

## What Changes

- 在用例准备阶段验证工作台入口，识别 HTTP 成功响应中的平台登录页面及明确的认证失效跳转。
- 工作台失效时先复用当前会话刷新；仍失效则由既有准备流程最多重新认证一次，并重新校验身份、上下文和工作台。
- 网络、权限及未知响应保持准备失败，不盲目提交凭据；业务步骤不自动重放。
- 增加同一上下文下部分认证失效的回归测试与只读真实 DSL。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `authenticated-session-reuse`：复用前必须确认工作台入口可用，不能仅凭业务 API 有效放行。

## Impact

涉及 `session_reuse.py`、认证复用测试、相关使用说明及真实用例。保留现有短信验证改动；不更改业务 DSL 操作语义，不改支付流程或默认浏览器 profile 策略。
