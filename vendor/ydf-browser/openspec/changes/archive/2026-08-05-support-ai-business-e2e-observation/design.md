## Context

参见 [proposal.md](proposal.md) 的 Why。当前 `run` 命令已经在 DSL 加载前确定 `run_id`、`report.json` 与 `events.jsonl`，`_EventLogger` 已提供带锁的逐行追加，`run_suite_specs` 已有串行分支；`WorkflowExecutor.run` 是所有步骤的共同执行循环，`PlaywrightRuntime` 已统一注册 request、response、requestfinished、requestfailed、console 和 pageerror 监听，请求转发也已在运行时共享路径中执行。因此本设计以扩展这些入口为主，不建立第二套 runner、executor 或 Playwright 监听体系。

设计同时受以下约束：

- AI 观察只为“AI 修改被测业务系统后验证”服务，普通测试回归必须保持默认轻量和兼容。
- 完整业务 API 正文具有最高诊断价值，但任何未脱敏内容都不能写入磁盘。
- 同步 Playwright 调用可能阻塞；心跳线程不能访问 DOM，普通线程取消也不能可靠中断同步 Playwright。
- 最终业务结论由 skill 与 AI 结合需求、源码和证据得出，工具只报告事实。
- 第一阶段不得增加第三方运行时依赖，也不得增加通用 `api.assert`。

详细契约以 [ai-development-observation-contract/spec.md](specs/ai-development-observation-contract/spec.md) 为准；相关边界决策见 `docs/adr/0004` 至 `docs/adr/0012`。

## Goals / Non-Goals

**Goals:**

- 用一个具体的 AI 观察会话贯穿 CLI、runner、executor 与 runtime，统一事件上下文、证据引用、脱敏和容量计数。
- 在不改变现有 `StepResult.success/message/data` 和二值退出码的前提下，增加稳定的 outcome、reason code 与业务断言回执。
- 即使 DSL 无效、浏览器卡住或进程被外部兜底终止，也尽可能留下可恢复的最后阶段和已完成证据。
- 复用现有网络、页面与转发观察点，保证业务 API 原始 URL、实际 URL和转发命中来自同一请求生命周期。

**Non-Goals:**

- 不把特定业务接口、菜单、字段、主键或 Bug 根因编码进运行时。
- 不自动从候选请求中选择“最终相关响应”，不实现 API 断言或业务修复建议。
- 不让普通回归默认承担 AI 观察的磁盘、内存、串行和超时成本。
- 不承诺在 `SIGKILL`、系统崩溃或断电后生成完整最终报告。

## Decisions

### 1. 使用一个具体观察会话扩展现有执行链

新增单个 `ydf_browser/observation.py`，提供具体的观察会话和少量纯函数；不定义抽象接口、工厂或插件体系。CLI 在确认 `--ai-observe` 后创建会话，并沿现有调用链把同一实例传给 runner、executor 与 runtime。普通模式传 `None`，继续执行原路径。

观察会话只负责：契约元数据、作用域与序号、事件/索引追加、原子文件写入、脱敏、容量计数、证据引用和超时状态。业务动作仍由现有 executor/runtime 完成，报告汇总仍由现有 runner 完成。

选择此方案是因为观察行为跨越四个现有模块且共享运行状态，集中后可以只实现一次安全边界。备选方案是在每个模块增加独立 logger/helper，但会重复序号、脱敏和容量逻辑；另一个备选方案是新建完整 observer 抽象层，第一阶段只有一个实现，没有收益。

### 2. 扩展 `_EventLogger`，不并行维护第二份运行事件流

`_EventLogger` 增加单调 `sequence`、统一观察信封和显式 flush，继续写现有 `events.jsonl`。观察会话通过它写 `run_started`、suite/case/step/phase 事件与 heartbeat；原有 `run_start` 等名称在 AI 模式映射为新契约事件，普通模式保持现状。

CLI 继续在 `_load_suite_specs` 前创建路径和首事件，因此 DSL 失败可以沿 `_cmd_run_validation_failed` 生成本轮 `blocked/dsl_invalid`。最终报告通过现有 `_write_json_file` 改为同目录临时文件加 `os.replace`；JSONL 不回写，只追加完整记录并 flush。

选择扩展现有 logger 是为了保持一个事实流和确定的先后顺序。另建 `ai-events.jsonl` 会让消费者在两条时间线之间对账，也不能提升可靠性。

### 3. AI 模式由父进程监督，浏览器执行保留在单个工作进程

AI 模式强制 `concurrency=1`。CLI 父进程负责墙钟、5 秒 heartbeat、最终状态和报告收尾；一个工作进程复用现有串行 `run_suite_specs`、登录、persistent profile 和 Playwright 生命周期。工作进程通过标准库进程队列向父进程发送 suite/case/step/phase 边界及最终结果，父进程据此维护步骤、用例和运行截止时间。

任一截止时间到达时，父进程先通过控制通道请求协作停止。工作进程在动作边界检查停止请求并关闭浏览器上下文；若同步 Playwright 调用未返回，父进程在短暂收尾窗口后终止整个工作进程，依据最后完整事件合成 `terminated/timeout`。外部 skill 的 30 秒 watchdog 仍是最后一级兜底，不伪造工具内部报告。

选择进程边界是因为同步 Playwright 对象具有线程归属，watchdog 线程直接关闭 page/context 或向执行线程注入异常都不可靠。只设置取消标志无法中断真正卡死的浏览器调用；把每个步骤放入独立进程又会破坏浏览器上下文和步骤状态。一个运行一个工作进程是满足可中断性且改动最小的边界。

父进程 heartbeat 只读取最近事件和单调时钟，不访问 DOM。网络正文和页面 artifact 由持有 Playwright 的工作进程完成脱敏和原子落盘；父进程只在文件完成后接收引用。

### 4. 在 `WorkflowExecutor.run` 的共同循环产生步骤事实和断言回执

现有 `progress_logger` 继续服务 stderr；新增观察回调在步骤开始、成功、失败和动作 phase 边界发送结构化事件。步骤结束后，executor 在唯一共同位置把 outcome 与 observation 附加到 `StepResult`，不改各 handler 的成功语义。

业务断言识别复用 `dsl._is_business_assertion_step`。回执从现有 handler 返回的 expected/actual、目标作用域、查询完成信号和匹配行事实中组装；缺少字段时记录不可用原因，不猜测。观察会话记录最近一个非断言步骤开始的网络序号，连续断言共享该起点，并把范围内候选 `request_id` 加入回执。工具不按 URL 或响应正文排序候选请求。

选择共同循环而不是逐个断言 handler 改造，可保证所有现有断言一致覆盖，也避免以后新增动作时复制信封逻辑。各 handler 只在当前 `data` 缺少必要业务事实时补最小字段。

### 5. 结果分类在现有报告汇总边界统一完成

`ExecutionReport` 与 `StepResult.to_dict()` 保持旧字段，AI 模式只新增 observation。runner 在形成 case report 时根据“是否到达可比较断言”“断言是否匹配”“是否超时/工具异常”统一映射为 `passed`、`assertion_failed`、`blocked` 或 `terminated`，并写稳定 `reason_code`；动作专属细节进入 `operation_reason`。

CLI 仍只返回 0 或现有非零失败码。skill 必须读取报告或最后事件，不能把 exit code 当细分类别。

选择报告汇总边界是因为 executor 只知道步骤事实，不知道用例是否因环境、前置条件或停止策略未到达业务断言；把分类散落到异常处理会产生相互矛盾的 reason code。

### 6. 网络证据复用现有 Playwright 与转发钩子，采用只追加生命周期

`PlaywrightRuntime._new_page` 继续是唯一页面监听注册点。现有 request/response/finished/failed handler 在 AI 模式额外调用观察会话，不再注册一套并行 listener。每个候选请求在 request 事件分配稳定的运行内序号 `request_id` 并立即追加 `request_started`；finished/failed 只追加一个终态。受控停止时，观察会话为仍打开的请求追加 `request_incomplete`。

采集资格使用浏览器原始 URL、当前环境 origin 和 resource type 判断。实际请求 URL、命中规则和转发结果直接复用 `request_forwarding.py` 已有匹配结果，并绑定到同一 `request_id`；不能由报告结束后重新匹配 URL 推断。

选择只追加 JSONL 是为了让强制终止时至少保留开始事实。原地更新 JSON 或先在内存中等待完整生命周期都会扩大崩溃丢失范围。

### 7. 脱敏先于持久化，结构化正文只保存语义表示

观察模块只使用标准库解析 URL、JSON、URL 编码表单和 XML。统一字段分类器先规范化大小写与常见分隔符，再执行规格中的精确敏感语义规则；URL、headers、console/page error 和正文共用该分类器。正文解析、脱敏与大小校验全部在内存中完成，成功后才原子写入私有运行目录。

JSON 保存脱敏后的完整结构；表单保存有序重复键值；XML 保存脱敏后的结构。`text/*` 无法安全识别结构、声明与内容矛盾、二进制、multipart 或超限内容只写原因和元数据，不写部分正文，也不计算正文哈希。单请求和单用例容量由观察会话计数，超过上限不影响浏览器流程。

选择语义表示而非保留原始字节，是因为安全脱敏会改变内容，继续宣称原始字节会误导诊断。流式通用脱敏器复杂且仍可能在临时文件留下秘密，第一阶段不采用。

### 8. 失败页面证据通过运行时现有状态采集集中触发一次

首个非通过步骤确定后，executor 请求 runtime 生成一次失败证据包。runtime 复用现有 page state、manifest、binding、notifications、console/page error 与表格作用域能力，新增安全截图和有界 DOM 摘要；不抓整页 HTML，不跨页扫描表格。

截图先枚举主页面和可见 frame 中的敏感控件并传给 Playwright mask；任一可见 frame 无法确认遮罩时跳过截图。DOM 摘要只读取可见语义节点和允许属性，按字节上限停止。表格断言优先复用断言时已经解析的有效业务行；超过 1 MiB 后只保留断言列加主键/编码列的前 10 行。

选择在失败点集中触发，是为了避免每步截图和 DOM 抓取的高成本及敏感面。成功断言只写小型回执。

### 9. readiness 与最终验证结论只由 skill 编排

gov-ydfdev-browser skill 在启动 CLI 前读取显式 readiness 清单。每项按 `http_reachable` 或 `semantic_probe` 执行；不根据转发前缀、端口或 URL 猜测前后端。`/_yms/ready` 作为用户明确给出的后端语义探针，webpack dev server 可使用 `http_reachable`；任意 HTTP 状态表示监听已建立，但 TLS 规则仍按输入执行。

skill 先从 `PATH` 解析已安装 `ydf-browser`，运行 `doctor --skip-config` 校验契约，再用同一可执行入口启动观察运行，并在运行后核对实际路径、版本、能力、断言回执、相关 API 正文和转发命中。它用标准库临时文件加 `os.replace` 写 `verification-result.json`，把“执行成功”和“业务变更 verified”分开；helper 不再接收源码根目录。

选择显式 readiness 输入，是因为当前转发参数没有服务类型语义，启发式猜测会把探活错误误报为业务失败。ready 只允许开始验证，真实请求命中才证明本地代码参与。

### 10. 冷启动试点验收同一个发布候选的默认安装物

实现和全量测试完成后，构建一个带新版本号的发布候选 ZIP 并冻结 SHA-256，从该包分别执行 runtime 与 skill 安装器写入默认目录。安装前记录旧 runtime 与 skill 指纹；验收只从默认安装的 `.agents/skills/gov-ydfdev-browser` 启动 helper，并由它调用 `PATH` 中解析出的已安装 `ydf-browser`。验证通过保留候选安装，验证失败恢复旧安装。

随后记录实际可执行文件路径、版本、契约能力、已安装 skill 和 helper 指纹，再启动无历史 `gpt-5.6-luna`、`xhigh` evaluator。evaluator 不得读取或调用 ydf-browser 源码目录，只得到规格允许的原始任务输入，通过冻结安装版 skill 完成修改前红灯、业务代码修改、两组新数据的连续绿灯和清理。

试点编排脚本只负责准备私有目录、记录业务仓库基线、启动 evaluator、检查指纹和汇总门禁，不包含 Bug 根因、业务响应选择或修复提示。若验证器/skill 有缺口，本次试点以 blocked 结束；修复后重新冻结并从新的红灯开始。

选择同一发布候选的默认安装物，是为了证明最终交付形态，而不是源码工作区的偶然状态。该验收不赋予提交、推送或清理用户已有改动的权限。

## Risks / Trade-offs

- [AI 模式增加一个工作进程，使报告收尾比普通运行更复杂] → 只在显式 AI 模式启用，普通路径不变；进程消息只传语义事件和最终可序列化结果，不传 Playwright 对象。
- [强制终止可能来不及截图或关闭浏览器上下文] → 父进程以已 flush 事件为最低保证，先请求协作停止再终止；报告明确 artifact 不可用原因，不伪造完整收尾。
- [完整结构化正文可能占用较多内存和磁盘] → 单正文 10 MiB、单用例 200 MiB 默认上限，先计量再解析，超限整块跳过且不中断业务流程。
- [字段名脱敏无法识别所有藏在普通自由文本中的秘密] → 自由文本只接受可安全解析的结构；console/page error 使用保守模式，边界不可靠时不保存文本。
- [截图 mask 依赖各 frame 可访问性] → 任一可见 frame 无法确认遮罩就放弃截图，使用 DOM 摘要、错误与网络证据替代。
- [候选请求范围可能包含多个业务请求] → 工具只列候选，skill/AI 依据业务唯一标识和源码选择；第一阶段不引入脆弱的自动相关性算法。
- [两次绿灯和清理增加试点耗时] → 这是防止偶发绿灯和残留测试数据的验收门禁，不在普通回归中执行。
- [默认目录安装会替换现有用户安装] → 安装前保存路径和指纹；失败时恢复旧安装，通过时保留已验证候选，避免同时维护两套默认入口。

## Migration Plan

1. 先增加观察契约数据结构、doctor 能力声明、CLI 参数校验、事件和报告兼容测试；默认模式保持原行为。
2. 接入 executor/runtime 共享观察点、脱敏和有界 artifact，并完成聚焦测试与完整 pytest。
3. 更新发行包内 skill 事实源与 references，使 helper 只调用 `PATH` 中安装的 CLI，验证 readiness、证据筛选与 `verification-result.json`。
4. 构建并审计同一个发布候选 ZIP，记录旧安装后把 runtime 与 skill 安装到默认目录，再冻结包、可执行文件和 skill 指纹。
5. 使用默认安装版执行冷启动真实业务 Bug 门禁；只有红灯、两次绿灯、清理和指纹复核全部完成后才关闭 change。

回滚时可停止传入 `--ai-observe`，普通运行路径继续可用。若 AI 模式在冷启动试点暴露契约缺口，则保持 change 未完成，修复后重新冻结并从红灯重跑；不降低门禁或复用旧试点证据。
