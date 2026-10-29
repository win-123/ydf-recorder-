## Why

慢速环境中，`open_menu` 当前在菜单页签出现并完成一次 DOM 扫描后即可成功，即使首次展示的业务工作面尚未挂载或自动查询仍未形成可操作结果。这会把真实失败推迟到下一组件动作，并使菜单性能耗时遗漏初始数据加载阶段。

## What Changes

- **BREAKING**：单据模板菜单只有在全部首次展示的运行时可见数据工作面进入类型对应的初始终态后才成功；到达步骤总超时仍未就绪时，`open_menu` 明确失败。
- 在浏览器触发前完成菜单解析、初始模板获取和 manifest 构建；单独记录浏览器触发到界面稳定的菜单业务稳定耗时，并保留完整自动化步骤总耗时。
- 以 100ms 周期动态重算首次展示工作面；优先接受加载或结果状态转换，没有转换证据时使用全页面共享的 500ms 稳定快照兼容兜底。
- 继续排除全页网络空闲：WebSocket、心跳、埋点、消息和其它后台请求不阻塞业务就绪；孤立 HTTP 失败只作为诊断证据。
- 请求继续按启动步骤归属，并在跨步骤完成时保留完成步骤，防止后台请求污染后续动作。
- 只有平台明确认定为非单据页面时才采用 open-only 成功标准；模板接口超时、HTTP 失败或响应无法解析必须明确失败。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `runtime-action-completion-signals`：把 `open_menu` 的完成标准从页签和一次扫描提升为动态工作面集合的初始终态，并规定失败、兼容兜底和 open-only 边界。
- `lightweight-execution-timing`：把菜单触发前准备与浏览器触发后的菜单业务稳定耗时分开记录。
- `performance-xlsx-report`：新增菜单业务稳定耗时及跨步骤请求完成上下文的报告语义，同时保持请求耗时与步骤墙钟时间相互独立。

## Impact

- 运行时与执行层：`ydf_browser/runtime.py`、`ydf_browser/executor.py`。
- 性能采集与导出：`ydf_browser/performance_xlsx.py` 及报告结构。
- 领域语言：`CONTEXT.md`。
- 测试：运行时、执行层、性能工作簿和真实慢速菜单用例。
- 不新增第三方依赖，不新增 DSL 字段。
