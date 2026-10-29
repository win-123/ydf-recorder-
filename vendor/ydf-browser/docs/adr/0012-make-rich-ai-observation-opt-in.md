# 将高成本 AI 观察设为独立模式

所有运行默认提供统一观察信封、原因码、语义阶段事件和基础失败证据；完整业务 API 文本报文、步骤级 console 和 page error 及 DOM 诊断等高成本采集只在 AI 开发验证模式启用，并由 skill 自动开启。测试人员现有普通回归不承担额外的大量磁盘和运行时成本，第二类场景则获得完成业务开发诊断所需的深层证据。

AI 开发验证模式使用显式 `ydf-browser run --ai-observe` 参数开启，并记录在报告元数据中；skill 自动传入该参数，不通过环境变量或调用者识别隐式启用。

该模式默认启用工具内受控的步骤、用例和整次运行超时，普通测试回归不继承这些新增默认限制。

首阶段 AI 开发验证模式只支持 `--concurrency 1`。它可以串行执行多个选中用例，但不承诺并发浏览器上下文之间的请求归属、容量统计和异常终止证据完整性。`--ai-observe` 与更高并发同时出现时，工具在浏览器启动前写出 `blocked/contract_incompatible` 报告和事件，并记录 `operation_reason=ai_observe_concurrency_unsupported`。普通回归运行继续沿用现有并发能力。

skill 为每次 AI 开发验证运行分配新的运行证据目录，并将目录内的 `report.json` 传给现有 `--report-file`。工具把 `events.jsonl` 和 `artifacts/` 写在同一目录，使全部路径在运行前即可确定。冷启动诊断试点根目录另有 `verification-manifest.json`、`evaluator-events.jsonl` 和 `evaluator-final.md`；红灯、第一次绿灯和第二次绿灯分别使用独立子目录。已完成目录不得复用，验收完成前不自动删除。`ydf-browser` 保持现有指定报告文件覆盖语义，避免改变测试人员普通回归行为。

skill 默认使用 `mktemp -d` 在代码仓库外创建权限为 `0700` 的系统临时试点根目录，避免完整业务报文被误提交或被仓库工具扫描。验收完成前保留全部证据，最终结果必须报告绝对路径和占用空间，并由用户决定保留或删除；只有用户显式指定输出目录时才覆盖该默认位置。

skill 不从转发路径或目标地址推断服务是前端、后端或其他类型。每个转发目标默认使用 `http_reachable` 就绪策略，完成 TCP、TLS 和 HTTP 交互即视为进程已监听，任意 HTTP 状态均可，连接拒绝、TLS 失败或超时表示不就绪；用户明确提供语义检查时使用 `semantic_probe` 覆盖默认策略，并校验指定 URL、状态码和响应内容。就绪策略及结果记录在验证清单中，真正的本地参与证明仍来自业务页面相关请求的实际转发命中。

每个 readiness 项使用最小字段 `target`、`mode`、`url`、`timeout_seconds` 和 `tls_verify`；`semantic_probe` 另有 `expected_status`、`json_path` 和 `equals`。`tls_verify` 默认 `true`，只能由用户提供的明确事实关闭，不能因目标看似本地而推断。超时按目标独立配置。特殊 TLS 或语义检查由 skill 执行，取代该目标的 `doctor --forward-target`，不扩展 `--forward` 或 `--forward-strip-prefix` 语法。
