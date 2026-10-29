# ai-development-observation-contract Specification

## Purpose
定义 AI agent 修改被测 YonDiF 业务系统后执行真实端到端验证所依赖的稳定观察契约、安全证据边界、skill 判定职责和冷启动验收门禁，使执行事实可诊断、业务结论可审计，同时保持测试人员普通回归兼容。

## Requirements

### Requirement: AI 观察模式必须显式启用且保持普通回归兼容
系统 SHALL 通过 `ydf-browser run --ai-observe` 显式启用高成本 AI 开发观察能力，并 MUST 保持普通回归的现有 DSL 语义、并发能力、报告字段和默认超时行为兼容。

#### Scenario: skill 开启 AI 观察模式
- **WHEN** gov-ydfdev-browser skill 为 AI 开发验证执行真实 DSL
- **THEN** skill MUST 显式传入 `--ai-observe`
- **AND** 报告和首个事件 MUST 记录 AI 观察模式已经启用

#### Scenario: 普通回归不承担高成本采集
- **WHEN** 调用者未传入 `--ai-observe`
- **THEN** 系统 MUST NOT 默认保存完整业务 API 正文、用例级 console/page error 全集或 AI DOM 诊断
- **AND** 系统 MUST NOT 应用 AI 模式新增的步骤、用例和运行超时默认值或串行限制

#### Scenario: AI 模式拒绝并发用例
- **WHEN** 调用者同时传入 `--ai-observe` 和大于 1 的 `--concurrency`
- **THEN** 系统 MUST 在浏览器启动前生成 `blocked/contract_incompatible`
- **AND** `operation_reason` MUST 为 `ai_observe_concurrency_unsupported`

### Requirement: AI 观察契约必须可预检和版本化
系统 SHALL 使用独立的 `contract_version` 和观察能力声明表达 AI 契约兼容性，并 MUST 复用现有 `ydf-browser doctor --skip-config` 作为浏览器启动前的预检入口。

#### Scenario: doctor 返回契约能力
- **WHEN** skill 运行 `ydf-browser doctor --skip-config`
- **THEN** 输出 MUST 包含 `tool_version`、`contract_version` 和 `capabilities.available`
- **AND** v1 可用能力 MUST 包含 `semantic_events`、`controlled_timeouts`、`failure_evidence_bundle`、`network_text_bodies`、`network_redaction`、`request_forward_provenance`、`case_console_page_errors`、`table_assertion_snapshot`、`business_assertion_receipts` 和 `atomic_evidence_writes`

#### Scenario: 契约不兼容时阻止运行
- **WHEN** doctor 缺少契约字段、契约主版本不受支持或缺少必要能力
- **THEN** skill MUST 使用 `blocked/contract_incompatible` 停止验证
- **AND** skill MUST NOT 尝试启动带 `--ai-observe` 的浏览器运行

#### Scenario: 运行后核对实际启用能力
- **WHEN** AI 观察运行已经开始
- **THEN** skill MUST 从首个事件和最终报告核对 `capabilities.enabled`
- **AND** 已声明可用但本次未启用的必要能力 MUST 视为 `blocked/contract_incompatible`

#### Scenario: 契约版本演进
- **WHEN** 契约增加向后兼容的字段或通用原因码
- **THEN** `contract_version` MUST 提升 minor 版本
- **AND** 已有字段、原因码或结果语义发生不兼容变化时 MUST 提升 major 版本

### Requirement: 观察契约必须在 DSL 校验前生效
系统 MUST 在 CLI 成功进入 `run` 编排后、浏览器启动前创建本次运行证据并写入首个 `run_started` 事件，然后再加载和校验 DSL。

#### Scenario: DSL 校验失败仍生成本轮证据
- **WHEN** DSL 解析或语义校验失败
- **THEN** 系统 MUST 不启动浏览器
- **AND** 系统 MUST 写出当前运行的最终报告和事件
- **AND** 结果 MUST 为 `blocked/dsl_invalid`

#### Scenario: CLI 参数无法解析
- **WHEN** CLI 参数在进入 `run` 编排前无法解析
- **THEN** 工具 MAY 不生成报告或事件
- **AND** skill MUST 依据 stderr 和缺失的 `run_started` 判为 `blocked/tool_error`
- **AND** skill MUST NOT 将其误报为 DSL 无效

### Requirement: 观察信封必须提供稳定的公共字段
系统 SHALL 为执行事件和步骤结果提供统一观察信封，同时 MUST 保留现有步骤 `success`、`message` 和 `data` 字段的名称及含义。

#### Scenario: 记录首个运行事件
- **WHEN** 运行编排开始
- **THEN** 第一条 `events.jsonl` 记录 MUST 为 `run_started`
- **AND** 该记录 MUST 包含 `tool_version`、`contract_version`、`capabilities`、`run_id` 和本次实际配置

#### Scenario: 记录后续语义事件
- **WHEN** 系统记录 run、suite、case、step 或动作 phase 事件
- **THEN** 事件 MUST 使用适用的 `sequence`、`timestamp`、`suite_id`、`case_id`、`step_id`、`event`、`phase`、`business_target`、`outcome`、`reason_code`、`operation_reason`、`duration_ms` 和 `evidence_refs`
- **AND** 当前阶段尚无事实值的字段 MUST 为空或省略，不能填入推测值

#### Scenario: 报告保持消费者兼容
- **WHEN** 系统生成 `report.json`
- **THEN** run 级元数据 MUST 重复契约版本和能力信息
- **AND** 步骤结果 MUST 在现有字段旁新增 `observation`
- **AND** 页面、网络、DOM 和完整错误集合 MUST 通过 `evidence_refs` 引用，不得内嵌到公共信封

### Requirement: 非通过结果必须区分断言、阻断和终止
系统 MUST 使用 `assertion_failed`、`blocked` 和 `terminated` 区分已获得可比较业务结果、尚未到达可比较结果和运行异常终止，并 MUST 使用稳定通用原因码与动作专属 `operation_reason` 分层表达事实。

#### Scenario: 业务断言结果不符合预期
- **WHEN** 查询已经确认完成、断言目标和表格作用域均可观察，但预期业务行不存在或实际值不符合 expected
- **THEN** 结果 MUST 为 `assertion_failed/assertion_mismatch`
- **AND** 工具 MUST NOT 直接输出 `business_bug` 结论

#### Scenario: 尚未获得可比较结果
- **WHEN** DSL、环境、前置条件、目标组件、必要证据、契约或工具问题导致业务断言无法完成
- **THEN** 结果 MUST 为 `blocked`
- **AND** v1 `reason_code` MUST 从 `dsl_invalid`、`environment_unavailable`、`prerequisite_unavailable`、`target_unavailable`、`evidence_unavailable`、`contract_incompatible` 或 `tool_error` 中选择

#### Scenario: 运行异常终止
- **WHEN** 运行发生工具内受控超时
- **THEN** 结果 MUST 为 `terminated/timeout`
- **AND** 外部终止由 skill 表达为 `terminated/external_termination`

#### Scenario: CLI 退出码保持二值兼容
- **WHEN** 所有选中用例通过
- **THEN** CLI 退出码 MUST 为 0
- **AND** 任意用例为 `assertion_failed`、`blocked` 或 `terminated` 时 MUST 沿用现有非零退出码
- **AND** skill MUST 从报告或最后事件读取具体结果，不得从不同非零数字推断

#### Scenario: 非终止结果沿用继续策略
- **WHEN** 用例结果为 `assertion_failed` 或 `blocked`
- **THEN** 系统 MUST 按现有 `suite.on_case_failure` 或 CLI 覆盖决定继续、停止测试集或停止运行
- **AND** 当前失败用例 MUST NOT 继续剩余步骤

### Requirement: 语义事件必须提供低噪声进度和心跳
系统 SHALL 记录运行、测试集、用例、步骤和动作阶段的开始、结束、失败、超时与诊断文件创建事件，并 MUST 排除逐次 locator、DOM 查询和浏览器重试轨迹。

#### Scenario: 长阶段输出 heartbeat
- **WHEN** 运行活跃且连续 5 秒没有新的语义事件
- **THEN** 系统 MUST 写入并 flush `heartbeat`
- **AND** 此后 MUST 每 5 秒重复，直到出现其他语义事件或运行结束
- **AND** heartbeat MUST 只记录当前作用域、已持续时间和最后事件序号，不得访问 DOM

#### Scenario: 进程异常后读取最后阶段
- **WHEN** 进程在最终报告前异常退出
- **THEN** 已完成的 JSONL 事件 MUST 已经 flush
- **AND** AI agent MUST 能从最后一条完整事件识别最后语义阶段

### Requirement: AI 模式必须提供受控超时
系统 MUST 在 AI 模式中提供步骤、用例和整次运行的墙钟超时，默认值分别为 120、900 和 1800 秒，并 SHALL 允许 skill 通过明确 CLI 参数覆盖。

#### Scenario: 覆盖超时配置
- **WHEN** skill 传入 `--step-timeout-seconds`、`--case-timeout-seconds` 或 `--run-timeout-seconds`
- **THEN** 参数 MUST 只与 `--ai-observe` 同时使用
- **AND** 参数 MUST 为正数并满足步骤上限不大于用例上限、用例上限不大于运行上限
- **AND** 实际生效值 MUST 写入 `run_started` 和最终报告

#### Scenario: 超时配置无效
- **WHEN** AI 超时参数不满足范围或顺序约束
- **THEN** 系统 MUST 在浏览器启动前生成 `blocked/contract_incompatible`

#### Scenario: 任一级超时终止整次运行
- **WHEN** 步骤、用例或运行超时首先到期
- **THEN** 系统 MUST 使用 `terminated/timeout`
- **AND** `operation_reason` MUST 分别为 `step_timeout`、`case_timeout` 或 `run_timeout`
- **AND** 系统 MUST 停止剩余步骤和用例、关闭当前浏览器上下文并尽力完成证据收尾

#### Scenario: 外部 watchdog 最后兜底
- **WHEN** 进程超过实际运行上限 30 秒仍未退出
- **THEN** skill MUST 先请求进程终止，仍无法退出时才强制杀死
- **AND** skill MUST 只依赖已 flush 证据表达 `terminated/external_termination`，不得伪造工具内超时报告

### Requirement: 每次 AI 运行必须使用独立且可恢复的证据目录
skill MUST 为每次 AI 运行预先分配新的证据目录，并 SHALL 通过现有 `--report-file` 把目录内 `report.json` 的确定路径传给工具；工具 MUST 在同目录写入 `events.jsonl` 和 `artifacts/`。

#### Scenario: 在运行前确定全部核心路径
- **WHEN** skill 准备执行一次 AI 观察运行
- **THEN** skill MUST 使用代码仓库外、权限为 `0700` 的新私有目录
- **AND** `report.json`、`events.jsonl` 和 `artifacts/` 的路径 MUST 在进程启动前可确定
- **AND** 已完成目录 MUST NOT 被后续运行复用或覆盖

#### Scenario: 流式与原子持久化
- **WHEN** 系统写入事件、网络索引或用例错误索引
- **THEN** 每条完整 JSONL 记录 MUST 立即 flush
- **AND** 正文、headers 和最终报告 MUST 在脱敏完成后通过同目录临时文件完整写入并原子替换
- **AND** 索引 MUST 只引用已经完成原子落盘的文件

#### Scenario: 强制终止后的有限保证
- **WHEN** 进程遭遇 `SIGKILL` 或系统崩溃
- **THEN** 系统只 MUST 保证已经 flush 的完整事件和索引行可读
- **AND** 系统 MUST NOT 承诺未完成正文、最终报告或断电级持久化

### Requirement: AI 模式必须采集有界的同源业务 API 证据
系统 SHALL 仅把浏览器原始 URL 与当前 YonDiF 环境同源、资源类型为 `xhr` 或 `fetch` 的候选请求纳入业务 API 索引，并 MUST 以原始 URL 判断采集资格、以实际 URL 和转发事实证明执行来源。

#### Scenario: 保存支持的文本业务正文
- **WHEN** 候选请求或响应明确声明为 JSON、`application/x-www-form-urlencoded`、XML 或可安全解析为这些结构的 `text/*`
- **THEN** 系统 MUST 保存经过脱敏的完整语义正文
- **AND** 转发后的本地 URL MUST NOT 改变该请求的采集资格

#### Scenario: 排除不支持的流量
- **WHEN** 流量属于认证请求、静态资源、页面文档、WebSocket、第三方请求、二进制、`multipart/form-data` 或无法确认类型的正文
- **THEN** 系统 MUST NOT 保存原始正文
- **AND** 同源 xhr/fetch 候选正文不支持时 MUST 在索引记录明确不可用原因

#### Scenario: 证明请求实际命中本地转发
- **WHEN** 业务请求匹配 `--forward` 或 `--forward-strip-prefix`
- **THEN** 索引 MUST 记录脱敏后的浏览器原始 URL、实际请求 URL、命中的规则、转发结果和响应状态
- **AND** skill MUST 依据与业务断言相关请求的实际命中判断本地代码是否参与验证
- **AND** 只有转发配置而无相关命中时 MUST 视为 `blocked/evidence_unavailable`

### Requirement: 网络索引必须使用只追加的请求生命周期
`artifacts/network/index.jsonl` MUST 为每个候选业务请求分配稳定 `request_id`，并 SHALL 使用单调递增 `sequence` 追加请求开始和唯一终态记录，不得回写既有 JSONL 行。

#### Scenario: 正常请求生命周期
- **WHEN** 候选业务请求出现并正常完成
- **THEN** 系统 MUST 立即写入并 flush `request_started`
- **AND** 完成后 MUST 追加 `request_completed`

#### Scenario: 失败或受控终止的请求生命周期
- **WHEN** 请求网络失败
- **THEN** 系统 MUST 追加 `request_failed`
- **AND** 受控超时收尾时尚未完成的请求 MUST 追加 `request_incomplete`

#### Scenario: 外部强制终止留下开始记录
- **WHEN** 外部强制终止发生在请求终态写入前
- **THEN** 索引 MAY 只存在 `request_started`
- **AND** skill MUST 将缺少终态解释为请求未完成

#### Scenario: 异步请求跨越步骤
- **WHEN** 请求开始与完成发生在不同 DSL 步骤或步骤间隙
- **THEN** 开始记录 MUST 包含 `started_step_id` 和 `started_phase`
- **AND** 终态 MUST 包含 `completed_step_id` 和 `completed_phase`
- **AND** 主要因果归属 MUST 以开始上下文为准，步骤间隙字段 MUST 为 null

### Requirement: 网络证据必须在落盘前安全脱敏
系统 MUST 在内存中完成 URL、headers 和结构化正文脱敏，且 MUST NOT 创建未脱敏临时文件、副本或正文哈希。

#### Scenario: 共用敏感字段分类器
- **WHEN** 系统处理 URL、headers、JSON、表单或 XML 字段名
- **THEN** 分类 MUST 大小写不敏感并忽略常见分隔符
- **AND** MUST 识别 password、passwd、token、secret、session、cookie、authorization、credential、API key 和 private key 语义
- **AND** 命中时 MUST 替换整个值并记录路径与规则名
- **AND** 普通 `code`、`key` 和 `id` MUST NOT 全局匹配，`ticket` MUST 只在认证语境匹配

#### Scenario: URL 脱敏
- **WHEN** 原始 URL、实际 URL 或转发规则进入证据
- **THEN** 系统 MUST 保留 scheme、host、port、path 及查询参数名称和顺序
- **AND** MUST 移除 userinfo 与 fragment，并把敏感参数值替换为 `[REDACTED]`

#### Scenario: headers 脱敏
- **WHEN** 系统保存请求头或响应头
- **THEN** headers MUST 分别写入独立 JSON 文件
- **AND** `Authorization`、`Proxy-Authorization`、`Cookie`、`Set-Cookie` 及名称包含 token、secret、session 或 api-key 的值 MUST 替换为 `[REDACTED]`
- **AND** header 名称、脱敏数量和非秘密业务上下文 MUST 保留

#### Scenario: 结构化正文脱敏
- **WHEN** 正文为 JSON、URL 编码表单或 XML
- **THEN** 系统 MUST 分别按字段名、键名、元素名和属性名脱敏
- **AND** `text/*` 只有安全解析为上述结构之一时才能保存
- **AND** 任意纯文本或结构化声明与内容不符时 MUST 记录 `redaction_unsupported` 且不得落盘正文

#### Scenario: 保存脱敏语义而非原始字节
- **WHEN** 结构化正文完成脱敏
- **THEN** 系统 MUST 以 `representation=redacted_semantic` 保存 UTF-8 证据
- **AND** JSON MUST 保留全部非秘密字段和值，表单 MUST 保留有序重复键值，XML MUST 保留脱敏后结构
- **AND** 索引 MUST 记录原始内容类型与 charset、原始大小和落盘大小

### Requirement: 网络证据必须受容量保护并解释不可用原因
系统 MUST 默认限制单个请求体或响应体为 10 MiB、单个用例累计网络 headers 与正文为 200 MiB，并 SHALL 允许仅在 AI 模式通过 `--max-network-body-bytes` 和 `--max-network-case-bytes` 覆盖。

#### Scenario: 正文超过容量上限
- **WHEN** 声明或实测正文大小超过生效上限
- **THEN** 系统 MUST NOT 保存截断或部分正文
- **AND** 索引 MUST 记录 `size_limit_exceeded`、声明或实测大小及请求摘要
- **AND** 浏览器业务流程 MUST 继续执行

#### Scenario: 使用稳定不可用原因
- **WHEN** 请求体或响应体没有可用文件
- **THEN** `capture_unavailable_reason` MUST 从 `not_present`、`unsupported_content_type`、`redaction_unsupported`、`size_limit_exceeded`、`body_read_failed`、`request_failed` 或 `incomplete` 中选择
- **AND** `not_present` MUST 表示该方向本来没有正文，不得被 skill 当作证据故障
- **AND** 其余原因只有在缺失内容与业务判断相关时才 MUST 导致 `blocked/evidence_unavailable`

### Requirement: 用例错误和页面证据必须安全且有界
AI 模式 SHALL 在整个用例期间记录 console error 和未捕获 page error，并 MUST 为每个非通过用例最多保存一张安全视口截图和一份有界 DOM 语义摘要。

#### Scenario: 保存用例错误
- **WHEN** 浏览器产生 console error 或未捕获 page error
- **THEN** 系统 MUST 记录时间、类型、来源位置及可用的步骤和阶段关联
- **AND** MUST 只处理 Playwright 已渲染 message 与 stack，不得展开 console 参数对象
- **AND** URL、Bearer/Basic 凭据、JWT 和可安全分隔的敏感字段值 MUST 在落盘前脱敏
- **AND** 无法可靠确定秘密边界时 MUST 不保存文本并记录 `redaction_unsupported`

#### Scenario: 采集安全失败截图
- **WHEN** 非通过用例的首个失败步骤确定且页面仍可用
- **THEN** 系统 MUST 采集一张当前视口截图而非全页截图
- **AND** password、认证 autocomplete 和名称命中敏感分类器的可见控件 MUST 使用 mask 遮罩
- **AND** 任一可见 frame 无法完成必要遮罩时 MUST 不保存截图并记录不可用原因

#### Scenario: 生成安全 DOM 摘要
- **WHEN** 系统生成失败 DOM 证据
- **THEN** 系统 MUST 生成有界语义摘要而非整页 `outerHTML`
- **AND** MUST 排除 script、style、隐藏控件值并脱敏敏感控件的 value、文本和相关属性
- **AND** 普通可见业务数据 MUST 保留

#### Scenario: 摘要失败相邻事件
- **WHEN** 系统生成失败证据摘要
- **THEN** 摘要窗口 MUST 为失败步骤开始前 5 秒至结束后 5 秒
- **AND** 工具 MUST NOT 为收集后置证据额外等待
- **AND** 完整用例网络和错误索引 MUST 不受摘要窗口裁剪

### Requirement: 所有非通过结果必须生成统一失败证据包
系统 MUST 为每个 `assertion_failed`、`blocked` 或工具内 `terminated` 用例尝试生成统一失败证据包，并 MUST 对任何无法采集的必需项目记录明确不可用原因。

#### Scenario: 生成通用失败证据
- **WHEN** 用例产生非通过结果
- **THEN** 证据包 MUST 包含失败步骤与阶段、业务目标、页面和前景层摘要、manifest 摘要、页面提示、可用安全截图和 DOM 摘要、相邻错误、失败请求摘要及绑定候选与排除原因
- **AND** 证据包 MUST 引用完整用例索引而不是内嵌全部原文

#### Scenario: 表格业务断言不符合预期
- **WHEN** 表格业务断言产生 `assertion_failed`
- **THEN** 证据包 MUST 包含表格语义身份与作用域、断言匹配值、查询完成信号、当前可见有效业务行数及可用分页或空状态
- **AND** 系统 MUST 优先保存当前渲染的全部有效业务行
- **AND** 序列化快照超过 1 MiB 时 MUST 退化为断言相关列和主键或编码列的前 10 行，并记录完整可见行数、样本行数和 `sample_truncated: true`
- **AND** 系统 MUST NOT 跨页抓取或以 DOM 行节点数代替业务行事实

### Requirement: 成功和失败业务断言必须生成结构化回执
系统 MUST 复用现有业务断言分类，为成功和不符合预期的断言记录 expected/actual、业务目标与作用域、匹配业务行和候选请求引用，且 MUST NOT 把回执本身解释为被测业务变更已验证。

#### Scenario: 识别现有业务断言
- **WHEN** 步骤为 `form.assert_values`、`notification.assert`、`workflow_result.assert`、`table.assert_column_values`、`table.assert_columns`、`table.assert_empty` 或 `table.assert_row_values`
- **THEN** 系统 MUST 生成业务断言回执
- **AND** `import.upload target.assert` MUST 继续只表示导入动作状态，不得替代后置业务断言

#### Scenario: 成功断言不生成高成本页面包
- **WHEN** 业务断言成功
- **THEN** 回执 MUST 记录断言 action、目标作用域、expected/actual、适用的查询完成信号、匹配行身份和相关列
- **AND** 系统 MUST NOT 因成功回执额外生成截图或 DOM 包

#### Scenario: 选择候选请求范围
- **WHEN** 系统为断言回执列出候选 `request_id`
- **THEN** 范围 MUST 从当前断言之前最近一个非断言 DSL 步骤开始，到当前断言完成为止
- **AND** 不存在前置非断言步骤时 MUST 从用例开始
- **AND** 连续断言 MUST 共用最近非断言步骤的起点
- **AND** 工具 MUST NOT 根据 URL 或响应内容自动选择最相关请求

#### Scenario: DSL 通过但绿色证据不足
- **WHEN** DSL 步骤全部成功，但 skill 无法找到相关完整 API 响应或证明相关请求命中本地转发
- **THEN** 运行事实只能称为执行成功
- **AND** skill MUST 使用 `blocked/evidence_unavailable` 表达变更尚未验证

### Requirement: skill 必须显式检查转发目标就绪而不推断服务类型
skill MUST 为每个转发目标使用显式 readiness 项，不得从转发路径或目标地址推断前端、后端或其他服务类型；就绪结果只表示可以开始验证，不得替代请求实际命中证明。

#### Scenario: 执行默认 HTTP 可达检查
- **WHEN** readiness 项使用 `mode: http_reachable`
- **THEN** 项 MUST 包含 `target`、`url`、`timeout_seconds` 和 `tls_verify`
- **AND** 完成 TCP、TLS 和 HTTP 交互即 SHALL 视为监听成功，任意 HTTP 状态均可
- **AND** 连接拒绝、TLS 失败或超时 MUST 视为 `blocked/environment_unavailable`

#### Scenario: 执行语义就绪检查
- **WHEN** 用户提供 `mode: semantic_probe`
- **THEN** 项 MUST 额外包含 `expected_status`、`json_path` 和 `equals`
- **AND** skill MUST 在独立超时内校验状态码和 JSON 值

#### Scenario: TLS 校验只能显式关闭
- **WHEN** readiness 项未明确提供 `tls_verify`
- **THEN** skill MUST 默认启用 TLS 校验
- **AND** skill MUST NOT 仅因目标地址是本地地址而自动关闭校验

### Requirement: skill 必须区分执行结果和最终变更验证结论
skill MUST 在私有试点根目录原子写入 `verification-result.json`，以 `verified`、`not_verified` 或 `invalid` 表达最终状态，并 SHALL 保持 `verification-manifest.json` 只记录输入、基线和指纹。

#### Scenario: 写入机器可读验证结果
- **WHEN** skill 完成或停止验证闭环
- **THEN** `verification-result.json` MUST 引用各次运行目录、工具 outcome、报告、业务断言回执、选定 `request_id`、API/UI 业务标识、本地转发命中、临时数据与清理结果及验证器指纹复核
- **AND** `evaluator-final.md` MUST 继续承载人类可读诊断

#### Scenario: 两次绿色但清理失败
- **WHEN** 两次绿色业务断言通过但临时数据清理在一次幂等重试后仍失败
- **THEN** 最终状态 MUST 为 `not_verified`
- **AND** 原因 MUST 为 `cleanup_failed`
- **AND** 结果 MUST 同时记录 `business_assertions_passed: true`、未清理唯一标识和最后已知状态

#### Scenario: 只有完整门禁才能 verified
- **WHEN** 红灯证据、两组新数据的连续绿色证据、全部临时数据清理和验证器指纹复核均通过
- **THEN** skill MUST 写入 `status: verified`
- **AND** 缺少任一门禁时 MUST NOT 写入 `verified`

### Requirement: ydf-browser 不得替代 AI 作业务根因判断
工具 MUST 只输出观察事实、结果分类、原因码和证据，不得根据任意业务响应结构推断业务主键、选择最终相关响应或宣称被测业务系统存在 Bug。

#### Scenario: AI 依据完整证据诊断业务
- **WHEN** 工具完成业务断言并保存候选 API 证据
- **THEN** skill 和 AI agent MUST 结合业务需求、唯一标识和源码选择相关响应并判断下一步
- **AND** 工具 MUST NOT 输出 `business_bug`、`bad_data` 或修复建议等业务推断

#### Scenario: 第一阶段不新增通用 API 断言
- **WHEN** 实现本 change
- **THEN** 系统 MUST NOT 新增通用 `api.assert` DSL
- **AND** 只有多个真实案例证明响应选择成为稳定瓶颈时才 SHALL 重新评估该能力

### Requirement: 冷启动真实业务试点必须作为完成门禁
本 change MUST 使用一个未知根因的独立 evaluator 完成真实业务 Bug 的修改前红灯和修改后连续绿色闭环；静态源码判断、合成故障、已知根因提示或直接浏览器操作均不得替代该门禁。

#### Scenario: 以指定弱模型无历史启动
- **WHEN** 启动冷启动 evaluator
- **THEN** evaluator MUST 使用 `gpt-5.6-luna` 和 `xhigh` 推理强度
- **AND** MUST 通过 `codex exec --ephemeral --disable memories --json` 禁用持久记忆后运行，并保存 `evaluator-events.jsonl` 和 `evaluator-final.md`
- **AND** 仅使用 `--ephemeral` 而未禁用 `memories` MUST NOT 视为无历史启动
- **AND** 输入 MUST 只包含原始 Bug 描述、业务仓库、转发参数、服务控制方式、用户明确提供的租户/默认组织/用户别名执行上下文和待验收 skill，不得包含根因、现成 DSL 或本次设计记录
- **AND** evaluator MUST 根据原始 Bug 自行编写真实 DSL，并在合格红灯和两次绿色验证中使用内容不变的同一 DSL

#### Scenario: 冻结验证器和 skill
- **WHEN** 试点开始
- **THEN** 系统 MUST 为同一个带新版本号的发布候选 ZIP 计算 SHA-256，并从该包分别执行 runtime 与 skill 安装器写入默认目录
- **AND** 用户目录下已安装 `ydf-browser`、`.agents/skills/gov-ydfdev-browser` 规范副本和 helper MUST 对 evaluator 只读并计算路径或内容指纹
- **AND** verification manifest MUST 使用 `agents_skill` 记录该唯一规范副本的目录指纹，并 MUST NOT 要求独立的 `codex_skill` 指纹
- **AND** 实际可执行文件路径、工具版本、契约版本和启用能力 MUST 进入私有验证证据
- **AND** 安装前 MUST 记录既有 runtime 与 skill 的路径和指纹；验证失败时 MUST 恢复既有安装，验证通过时 MUST 保留已验证候选
- **AND** 试点结束时任一验证器或 skill 指纹变化 MUST 使结果为 `invalid`
- **AND** 目录指纹 MUST 覆盖安装包内文件，但 MUST 排除缓存、报告等运行产物

#### Scenario: 保护业务仓库已有改动
- **WHEN** 业务仓库在试点开始前存在脏工作区
- **THEN** skill MUST 记录 HEAD、porcelain 状态、修改和未跟踪文件清单及 SHA-256，并在私有目录保存必要基线
- **AND** evaluator MUST NOT reset、clean 或还原用户已有改动
- **AND** 已有脏文件被意外改变 MUST 产生 `invalid/preexisting_change_modified`
- **AND** 修复确需重叠修改时 MUST 分别表达基线内容和 evaluator 新增差异

#### Scenario: 修改前必须先获得真实红灯
- **WHEN** evaluator 准备修改业务代码
- **THEN** evaluator MUST 已经通过默认目录中的冻结 skill 和安装版工具执行真实 DSL
- **AND** evaluator MUST 在首次运行前创建并冻结 `verification-manifest.json`；skill 的每次运行入口 MUST 要求该清单、核对 DSL 与 readiness 路径并记录清单 SHA-256
- **AND** evaluator MAY 在合格红灯前保持同一 DSL 路径并修订内容；每次运行 MUST 记录实际 DSL SHA-256，合格红灯后 MUST 锁定内容
- **AND** 在取得合格红灯前 MUST NOT 写入业务仓库中的任何文件；临时日志、诊断探针、埋点或计划随后回退的修改均视为违规并使试点无效
- **AND** 红灯 MUST 到达与 Bug 相关的业务断言
- **AND** API 与 UI 双层证据 MUST 围绕同一临时业务唯一标识证明修改前前置条件和修改后异常结果
- **AND** 合格运行 MUST 在同一 skill helper 运行目录内包含前置查询、业务修改和后置断言三个不同的已完成请求；诊断用直接浏览器或 API 调用不得补齐其中任一阶段

#### Scenario: 修改后必须连续获得两次绿色
- **WHEN** evaluator 完成业务代码修改并确认新服务就绪
- **THEN** evaluator MUST 使用红灯时的同一 DSL 和两组新的、互不复用的临时业务数据连续执行两次绿色验证
- **AND** 最终结果 MUST 机器校验合格红灯和两次绿色运行记录的 DSL SHA-256 完全一致
- **AND** 最终结果 MUST 机器校验红灯与两次绿色的 API/UI 业务标识各自一致且三组标识互不复用
- **AND** 最终结果 MUST 依据每个运行目录的 `external-result.json`、报告、网络索引和正文证据，校验前置查询、业务修改和后置断言请求按顺序由同一次冻结 skill 运行产生；前置查询、业务修改和绿色后置请求 MUST 携带该次业务标识，红灯的负向后置响应仅可在选定请求由同目录真实失败断言回执引用时不包含已消失的业务标识
- **AND** 每次相关保存和查询请求 MUST 实际命中预期本地转发目标
- **AND** 两次运行 MUST 分别使用新的证据目录并完成临时数据清理

#### Scenario: E2E 必须经过冻结 skill
- **WHEN** evaluator 取得红灯或绿色证据
- **THEN** 证据 MUST 由默认安装的冻结 gov-ydfdev-browser skill helper 调用 `PATH` 中已安装的 `ydf-browser` 产生
- **AND** helper、`ydf-browser` 子进程和 evaluator MUST NOT 读取或调用 ydf-browser 源码目录或解压目录
- **AND** Playwright 脚本、浏览器 MCP、人工点击或直接 API 调用 MUST NOT 替代 UI 断言
- **AND** 额外 API 调用 MAY 辅助诊断但 MUST NOT 计入门禁

#### Scenario: evaluator 不扩大到代码交付权限
- **WHEN** evaluator 修改和验证业务系统
- **THEN** evaluator MUST NOT 执行 git add、commit、push、rebase 或分支切换
- **AND** 最终结果 MUST 只引用相对业务工作区基线的本地差异，由用户决定是否提交

#### Scenario: 工具缺口使本次试点停止
- **WHEN** 冷启动 evaluator 发现冻结验证器或 skill 缺少完成试点所需能力
- **THEN** 本次试点 MUST 以 blocked 停止
- **AND** 修复工具后 MUST 从新的修改前红灯运行重新开始，不得在同一试点中边测边改验证器

### Requirement: 错误提示必须关联候选业务请求
系统 MUST 在 AI 观察模式下，为由未处理 error notification 触发的非通过失败证据包生成 `notification_request_associations`，表达页面错误提示与业务 API 请求之间的确定性关联或未决候选关系。

#### Scenario: 声明错误提示关联能力
- **WHEN** skill 运行 `ydf-browser doctor --skip-config` 或读取 AI 观察运行的 `run_started`
- **THEN** `capabilities.available` 或 `capabilities.enabled` MUST 包含 `notification_request_associations`
- **AND** `contract_version` MUST 使用兼容 minor 版本表达该新增字段

#### Scenario: 确认 YonDiF 统一业务错误响应
- **WHEN** 当前失败步骤因未处理 `type=error` 页面提示失败
- **AND** 失败证据候选范围内存在唯一已完成业务请求，其脱敏 JSON 响应正文满足 `code === 999`
- **AND** 该响应正文的 `message` 与页面提示文本精确一致
- **THEN** 失败证据包 MUST 包含一条 `status=confirmed` 的 `notification_request_associations` 记录
- **AND** 该记录 MUST 包含提示类型与文本、`evidence_basis=yondif_code_999_message_exact`、`request_id`、HTTP 方法、响应状态、浏览器原始 URL、实际请求 URL、转发结果摘要，以及响应正文路径

#### Scenario: 未决候选不排序
- **WHEN** 页面错误提示附近存在业务请求，但不存在唯一确定性正文匹配或共同请求标识证据
- **THEN** 失败证据包 MUST 包含 `status=unresolved` 的关联记录
- **AND** 该记录 MUST 包含未决原因和候选 `request_id`
- **AND** 系统 MUST NOT 根据 HTTP 状态、URL 相似性、时间邻近或通用 HTTP 200 业务 envelope 生成“最可能请求”或根因判断

#### Scenario: 候选范围沿用失败证据窗口
- **WHEN** 系统为错误提示生成关联候选
- **THEN** 候选范围 MUST 复用失败步骤开始前 5 秒至结束后 5 秒内开始或完成的业务请求
- **AND** 在失败步骤内已启动但证据包生成时尚未完成的请求 MUST 以候选 `request_id` 保留，并记录终态或正文不可用原因
- **AND** 系统 MUST NOT 为等待后置响应额外延迟失败收尾

#### Scenario: 保持失败请求摘要兼容
- **WHEN** HTTP 200 业务响应因错误提示关联进入 `notification_request_associations`
- **THEN** 系统 MUST NOT 仅因该业务响应表示错误而把它加入 `failed_requests`
- **AND** `failed_requests` MUST 继续只表达网络失败、不完整请求或 HTTP 非成功状态的既有摘要语义

#### Scenario: 预期错误提示不触发关联失败包
- **WHEN** 点击动作捕获 error notification 且下一步紧接 `notification.assert` 将其声明为预期结果
- **THEN** 当前点击步骤 MUST 保持成功
- **AND** 系统 MUST NOT 仅因该预期提示生成失败证据包或 `notification_request_associations`

### Requirement: 可见字段约束具有可追溯观察证据

AI 观察模式的 DOM 摘要 MUST 保留可见控件的关联字段标签、必填状态及来源、公开原生约束属性和输入提示。该信息 MUST 仅描述当前界面证据，不改变测试 DSL、动作结果或保存校验。

#### Scenario: 平台标签标记必填
- **WHEN** 可见控件的同一表单项可见标签具有平台必填标记
- **THEN** 摘要 MUST 将该控件标为必填，并记录标签来源与字段标签
- **AND** MUST NOT 将其他表单项或其他 frame 的同名标签用于该控件

#### Scenario: 原生必填与未知状态
- **WHEN** 控件具有原生 required 或显式 aria-required 声明
- **THEN** 摘要 MUST 保留必填状态及证据来源，正向必填证据优先
- **AND** 缺少显式必填证据时 MUST 输出未知，MUST NOT 以未标记推断可选

#### Scenario: 格式与长度约束仅保留公开事实
- **WHEN** 可见控件声明 type、pattern、minlength、maxlength、min、max、step 或 placeholder
- **THEN** 摘要 MUST 保留对应公开属性及提示
- **AND** MUST NOT 将提示、字段名称或静态模板解释为完整业务正则或动态必填规则

#### Scenario: 安全和运行边界
- **WHEN** 采集包含敏感控件、隐藏控件或超出预算的信息
- **THEN** 系统 MUST 沿用脱敏、可见性和大小限制，并明确标记约束文本截断；新增提示及约束属性不得泄漏敏感控件内容
- **AND** 未启用 AI 观察时 MUST NOT 增加采集或改变普通测试结果

#### Scenario: 编写者使用约束证据
- **WHEN** 技能指导编写新增录入用例
- **THEN** 技能 MUST 要求先核对当前字段约束和未知项，再生成最小录入数据
- **AND** MUST 说明保存提示仍可能暴露未公开的业务校验，不将提示或公开属性视为穷尽约束
