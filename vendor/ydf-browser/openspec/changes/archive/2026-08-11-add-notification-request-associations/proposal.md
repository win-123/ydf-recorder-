## Why

AI 开发验证里已经能采集 HTTP 200 的业务 API 正文，但失败摘要只突出非 200 或网络失败请求。YonDiF 业务错误常以 HTTP 200 返回并由前端 `code === 999` 响应拦截器弹出错误提示，导致 agent 捕获到 error notification 后仍可能因为“没有非 200 请求”把问题交给用户裁决。

## What Changes

- 在 `--ai-observe` 失败证据包中新增 `notification_request_associations`，把未处理 error notification 与候选业务 API 请求建立可审计关联。
- 对 YonDiF 平台统一业务错误提供确定性匹配：动作范围内唯一 `code === 999` 响应正文的 `message` 精确等于错误提示文本时，关联状态为 `confirmed`。
- 对其他 HTTP 200 业务 envelope、HTTP 非成功状态、时间邻近或 URL 相似请求只列为 `unresolved` 候选，不排序、不推断根因。
- 保留 `failed_requests` 既有语义，不把任意 HTTP 200 业务响应改成失败请求。
- 更新 agent 消费规则：遇到 error notification 时先看关联结果；没有新字段的旧运行也必须检查 HTTP 200 response body，不能只看非 200 请求。

## Capabilities

### New Capabilities

### Modified Capabilities

- `ai-development-observation-contract`: 失败证据包新增页面错误提示与业务 API 请求的关联摘要。

## Impact

- 影响 `ydf_browser` 的 AI 观察失败证据包生成逻辑和相关测试。
- 影响 OpenSpec 契约、领域文档、ADR 和 `gov-ydfdev-browser` skill 消费说明。
- 不新增 CLI 参数，不新增外部依赖，不改变普通回归默认行为。
