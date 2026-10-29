# 使用统一的 AI 观察信封

每个 DSL 步骤和执行事件使用统一的观察信封表达运行身份、当前阶段、业务目标、事实结果、页面语义状态、计时和诊断文件引用，动作专属结果继续保留在独立详情中。现有步骤 `data` 保持兼容，避免一次性重写全部报告消费者；AI 可以先解析公共信封，仅在需要时读取动作专属详情。

`events.jsonl` 第一条 `run_started` 事件记录 `tool_version`、`contract_version`、`capabilities`、`run_id` 和本次实际配置，保证最终报告缺失时事件流仍可自描述。后续事件只使用以下最小公共字段：

- `sequence`、`timestamp`
- `suite_id`、`case_id`、`step_id`
- `event`、`phase`、`business_target`
- `outcome`、`reason_code`、`operation_reason`
- `duration_ms`、`evidence_refs`

字段在相应阶段没有事实值时使用空值或省略，例如开始事件尚无最终 `outcome`。`report.json` 在 run 级重复契约元数据，并在现有步骤结果旁新增同结构的 `observation`；现有 `success`、`message`、`data` 不删除、不改名，动作专属详情继续放在 `data`。页面状态、网络正文、DOM 和完整错误集合只通过 `evidence_refs` 引用，不内嵌观察信封。

`contract_version=1.2` 兼容继承 `1.0` 的以下通用原因码：

| 结果 | 通用原因码 |
|---|---|
| `assertion_failed` | `assertion_mismatch` |
| `blocked` | `dsl_invalid`、`environment_unavailable`、`prerequisite_unavailable`、`target_unavailable`、`evidence_unavailable`、`contract_incompatible`、`tool_error` |
| `terminated` | `timeout`、`external_termination` |

动作特有事实写入 `operation_reason` 和结构化详情，例如 `expected_row_missing`、`table_scope_not_found`、`step_timeout` 或 `local_backend_not_reached`。工具不输出 `business_bug`、`bad_data` 等需要业务上下文才能成立的推断性原因码，也不在通用原因码中编码修复建议。

新增通用原因码提升契约 minor 版本；改变已有原因码、字段或结果的语义提升 major 版本。skill 遇到未知 minor 版本字段时忽略未知扩展，遇到不支持的 major 版本时使用 `blocked/contract_incompatible` 明确阻断，不猜测字段含义。

stdout 摘要、报告和事件记录 `tool_version`，观察信封使用独立的 `contract_version` 并声明本次实际启用的观察能力。

`capabilities` 使用 `available` 和 `enabled` 两个数组：前者表示当前工具版本支持，后者表示本次运行实际开启。`contract_version=1.2` 兼容继承 `1.0` 的以下能力名，并新增错误提示请求关联与验证入口声明能力：

- `semantic_events`
- `controlled_timeouts`
- `failure_evidence_bundle`
- `network_text_bodies`
- `network_redaction`
- `request_forward_provenance`
- `case_console_page_errors`
- `table_assertion_snapshot`
- `business_assertion_receipts`
- `notification_request_associations`
- `verification_entrypoint`
- `atomic_evidence_writes`

`workflow_result` 是额外的 DSL 组件能力，不属于 AI skill 启动前必须启用的观察能力：它始终出现在 `capabilities.available`，只有本次实际执行 `workflow_result.assert`、`workflow_result.details` 或 `workflow_result.confirm` 时才加入 `capabilities.enabled`。

`business_assertion_receipts` 表示成功和不符合预期的业务断言均能输出结构化 expected/actual、业务目标与作用域、匹配业务行及候选请求引用。skill 将它列为 AI 开发验证的必要能力。网络 headers、生命周期索引和安全截图分别归入已有 `network_text_bodies`、`network_redaction` 和 `failure_evidence_bundle`，不再拆分更多 capability。

skill 检查 AI 开发验证所需能力；缺少或未启用必要能力时使用 `blocked/contract_incompatible`。能力已经启用但本次具体证据采集失败时使用 `evidence_unavailable`，不能误报为工具不支持该能力。

运行前兼容性检查复用现有 `ydf-browser doctor`，不新增 capability 子命令。`doctor` 始终输出 `tool_version`、`contract_version` 和 `capabilities.available`；skill 在启动真实浏览器前运行 `doctor --skip-config` 检查契约主版本和必要能力，本地转发场景可继续使用现有 `--forward-target` 做连通性检查。旧版本 `doctor` 缺少契约字段、不支持主版本或缺少必要能力时，skill 使用 `blocked/contract_incompatible` 停止，不尝试带 `--ai-observe` 运行。真实运行后再从首个 `run_started` 事件和报告检查 `capabilities.enabled`。

AI 观察契约在 CLI 成功进入 `run` 编排后、浏览器启动前生效：先创建本次运行证据并写入 `run_started`，再加载和校验 DSL。DSL 解析或语义校验失败必须写出最终报告与事件，结果为 `blocked/dsl_invalid`，不得启动浏览器。CLI 参数解析失败发生在运行编排之外，无法承诺生成报告；skill 依据 stderr 和缺失的 `run_started` 将其判为 `blocked/tool_error`，不得误报为 DSL 无效。
