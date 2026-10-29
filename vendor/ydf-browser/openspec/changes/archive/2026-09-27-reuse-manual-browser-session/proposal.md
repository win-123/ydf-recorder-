## Why

无 DSL 手工浏览器会话每次清 cookies 并重新登录，短时间关闭重开会重复发送短信并触发限流。需要共享已有认证复用能力。

## What Changes

- 手工会话按实际环境和账号复用认证，支持 --force-login。
- 使用现有 cookies 差量同步，在手工等待期间采集状态，正常关闭后保存最后有效快照。
- 保留手工选择租户、组织和年度的行为，不生成 DSL 报告。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `authenticated-session-reuse`: 将按身份复用范围扩展到手工会话。
- `manual-browser-session`: 定义认证复用、关闭收尾与强制登录。

## Impact

影响 CLI 手工入口、运行时等待循环及对应测试和使用文档；不增加依赖。
