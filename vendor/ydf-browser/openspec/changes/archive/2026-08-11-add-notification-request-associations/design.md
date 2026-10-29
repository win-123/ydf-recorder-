## Context

现有 `--ai-observe` 已经保存同源 xhr/fetch 的 HTTP 200 response body，并在失败证据包里提供相邻错误和 `failed_requests` 摘要。但 `failed_requests` 只覆盖网络失败、不完整请求和 HTTP 非成功状态，无法暴露 YonDiF 常见的 HTTP 200 业务错误。平台统一 axios 拦截器会在 `code === 999` 时只把 `message` 传给 `Message.error`，提示 DOM 本身没有 URL、XHR 或 trace 元数据。

## Goals / Non-Goals

**Goals:**

- 在 error notification 造成步骤失败时，给 AI agent 一个可直接读取的请求关联事实。
- 保持证据紧凑，只引用既有网络索引和正文路径。
- 证明请求执行来源，包括原始 URL、实际 URL 和转发结果。
- 对确定性匹配使用 `confirmed`，不确定时使用 `unresolved`。

**Non-Goals:**

- 不让工具判断业务 Bug、本地服务错误或环境噪音。
- 不把所有 HTTP 200 业务失败纳入 `failed_requests`。
- 不依赖前端调用栈作为首阶段必要信号。
- 不新增 CLI 参数或 URL allowlist。

## Decisions

1. 关联逻辑放在失败证据包生成阶段。
   - 方案：生成失败证据包时读取已经采集的网络 request records 和 response body path，构造 `notification_request_associations`。
   - 原因：已有网络采集层已经保存所需正文和请求执行来源；在采集层增加通用业务失败分类会扩大 `failed_requests` 语义。
   - 放弃方案：把 HTTP 200 `success:false` 或非零业务码统一塞进 `failed_requests`。这会把无通知的后台业务响应也变成失败摘要，重新引入噪声。

2. 首阶段只确认 YonDiF `code === 999` 与提示文本精确匹配。
   - 方案：解析已脱敏 JSON response body，若 `code` 数值或字符串等于 `999` 且 `message` 精确等于 notification message，并且候选集中唯一，则输出 `confirmed`。
   - 原因：这是平台统一错误提示链的确定性证据；toast 文本和时间邻近不足以唯一归因。
   - 放弃方案：模糊匹配、按 URL 打分、用调用栈跨 Promise 归因。它们会产生看似确定但不可审计的结论。

3. `unresolved` 候选只列事实，不排序。
   - 方案：候选范围复用失败步骤相邻窗口和步骤内已启动请求，记录 candidate request IDs 和未决原因。
   - 原因：AI 仍可继续读取 HTTP 200 正文和本地日志；工具不替代诊断。

4. agent 消费规则同步更新，但兼容旧 runtime。
   - 方案：skill 先读 `notification_request_associations`；字段不存在时仍要求人工检查 `artifacts/network/index.jsonl` 中 HTTP 200 response body。
   - 原因：已安装工具升级前，agent 也不能继续只看非 200 请求。

## Risks / Trade-offs

- 并发相同错误消息可能导致 `unresolved` 增多 -> 保持唯一匹配要求，宁可未决也不误归因。
- 响应正文缺失或超限会阻止确认 -> 记录正文不可用原因，AI 再判断是否构成证据不足。
- 只覆盖 `code === 999` 首阶段较窄 -> 后续如有真实非统一业务错误案例，再增加明确 envelope 规则和测试。

## Migration Plan

- 契约 minor 版本增加向后兼容字段和能力名。
- 旧报告没有 `notification_request_associations` 时，skill 按更新后的兼容说明继续检查 HTTP 200 response body。
- 回滚时删除字段生成逻辑即可；既有报告消费者应忽略未知字段。
