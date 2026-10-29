# 区分执行成功与变更已验证

`ydf-browser` 的绿色结果只表达 DSL 步骤执行成功，并在观察结果中汇总已声明、已执行、通过和不符合的业务断言；它不直接宣称被测业务系统变更已验证。skill 和 AI agent 必须结合需求或 Bug 修改判断已执行断言是否覆盖本次变更，没有相关业务断言的绿色运行不能作为 AI 开发验证通过的证据。

第一阶段使用一个 OpenSpec change 统一交付工具观察契约与运行时、gov-ydfdev-browser skill 更新、自动化测试和真实 Bug 冷启动验收。工具、skill 或测试单独完成都不能关闭该 change，避免出现观察能力已经声明但消费方式或真实业务闭环尚未证明成立的中间完成状态。

该 change 只新增一个能力规格 `ai-development-observation-contract`，统一约束 AI 模式 CLI、兼容性预检、结果与事件信封、受控超时、网络和页面证据、脱敏、成功断言回执、skill 结果及冷启动门禁。现有表格断言、请求转发和普通报告规格只在原有语义确实变化时增加最小 delta，不按证据类型拆分多个新规格；具体设计取舍继续由 ADR 0004–0012 承载。

每个成功业务断言在报告中生成轻量的成功断言回执，记录断言 action、业务目标和表格作用域、expected 与实际匹配值、查询完成信号、命中业务行身份及断言相关列，以及断言时间窗口内的候选 `request_id` 和候选请求的本地转发命中事实；成功时不额外生成截图或 DOM 包。skill 必须读取候选请求的完整 API 响应并围绕同一业务唯一标识形成 API 与 UI 双层绿色证据。DSL 执行通过但找不到相关 API，或不能证明相关请求命中本地转发目标时，只能称为执行成功，验证结论为 `blocked/evidence_unavailable`，不得称为变更已验证。

候选请求范围从当前断言之前最近一个非断言 DSL 步骤的开始时间起，到当前断言完成时间止；若不存在前置非断言步骤，则从用例开始。请求在范围内开始或完成都列为候选，范围内启动但稍后完成的请求继续通过 `request_id` 保留关联。连续多个断言共用最近的非断言步骤，不因前一个断言切断查询请求。工具不根据 URL 或响应内容选择“最相关”请求，最终选择仍由 skill 完成。

回执生成范围直接复用现有 `_is_business_assertion_step`：`form.assert_values`、`notification.assert`、`workflow_result.assert`、`table.assert_column_values`、`table.assert_columns`、`table.assert_empty` 和 `table.assert_row_values`。`import.upload target.assert` 仍只表示导入动作状态，不生成业务断言回执，现有 DSL 校验继续要求 `submitted` 后存在独立业务断言。工具生成回执不表示断言足以覆盖本次需求或 Bug，相关性仍由 skill 判断。

第一阶段必须通过一个冷启动诊断试点验收：未预先获知根因的 AI agent 可以先阅读被测业务系统源码形成根因假设，但不能用静态判断代替真实验证。修改业务代码前必须使用真实 DSL 复现相关业务断言红灯；修改后必须确认新代码已经生效，并使用同一 DSL 和两组新的验证用临时数据连续获得绿色结果，最后清理临时数据。

试点使用不继承本次设计对话的独立 agent，并遵循以下隔离和执行顺序：

1. 使用无历史上下文方式启动，只提供原始 Bug 描述、业务仓库、转发参数、服务控制方式、用户明确提供的租户/默认组织/用户别名执行上下文和待验收 skill；不提供根因、现成 DSL、现成诊断或本次探索记录。evaluator 必须根据 Bug 自行编写真实 DSL，可以自行阅读业务源码并形成假设。

红灯和两次绿灯必须通过冻结的默认目录安装版 gov-ydfdev-browser skill 调用同一发布候选安装到 `PATH` 的 `ydf-browser` 执行。evaluator 不得读取或调用 ydf-browser 源码目录或发布包解压目录，也不得使用 Playwright 脚本、浏览器 MCP、人工点击或直接 API 调用替代 UI 断言；可以读取业务源码、运行聚焦测试、控制服务和分析已保存的 API 报文，额外 curl 或 API 调用只能辅助诊断，不计入红灯或绿色门禁。`evaluator-events.jsonl` 必须能够审计三次运行确实经过 skill。

待验收 skill 的明确事实源是用户目录下 `.agents/skills/gov-ydfdev-browser`，evaluator 启动时解析其绝对路径并仅写入私有验证清单。skill 指纹覆盖整个目录的相对路径和文件内容，不只覆盖 `SKILL.md`。Codex 直接发现该规范副本，Claude Code 通过入口链接使用同一份内容；试点开始与结束只复核该规范副本及 helper 指纹，任一变化都使试点 `invalid`。仓库文档不保存具体用户名或本机绝对路径。
2. 本试点固定使用 `gpt-5.6-luna` 和 `xhigh` 推理强度。若当前协作 subagent 接口未暴露该模型，不得替换成其他模型，应使用 `codex exec --ephemeral --disable memories --json --output-last-message evaluator-final.md --model gpt-5.6-luna -c 'model_reasoning_effort="xhigh"'` 启动独立临时 Codex CLI 进程，并把 JSONL 输出保存为试点根目录的 `evaluator-events.jsonl`。`--ephemeral` 只禁止保存会话，不能替代 `--disable memories`；未显式禁用持久记忆的 evaluator 不满足无历史门禁。
3. 试点开始前冻结发布候选 ZIP、默认目录安装版 `ydf-browser` 和配套 skill，试点期间对 evaluator 只读。skill 必须在首次运行前于试点根目录生成并冻结 `verification-manifest.json`，记录 evaluator 模型与推理强度、发布包 SHA-256、工具版本、观察契约版本、能力列表、已安装 runtime 与 skill 指纹、业务仓库修改前的提交与脏工作区摘要、转发规则，以及红灯和两次绿灯使用的 DSL 文件 SHA-256。skill 的每次 `run` 必须要求该清单、核对 DSL 与 readiness 路径并记录清单 SHA-256；缺少清单或首次运行后才补写均使试点无效。试点结束时重新计算工具和 skill 指纹；任一变化都使本次验收无效。

业务仓库允许在试点开始前已有用户改动。skill 记录 HEAD、`git status --porcelain`、已修改和未跟踪文件清单及 SHA-256，并把基线 diff 与必要的未跟踪文件副本保存在私有试点目录。evaluator 不得 reset、clean 或还原已有改动；最终业务修改按试点开始快照到结束状态计算，而不是直接相对 HEAD。已有脏文件被意外改变时使用 `invalid/preexisting_change_modified`；若修复确实必须修改同一文件，则结果必须分别表达基线内容和 evaluator 新增差异。
4. evaluator 只允许修改被测业务系统和生成 DSL 与证据；发生工具能力缺口时以 `blocked` 结束本次试点，由独立实现流程修复工具后从新的红灯运行重新开始，不能在同一次试点中边测边改验证器。

evaluator 可以运行测试、通过 IDEA MCP 重启本地服务并完成三次 E2E，但不得在业务仓库执行 `git add`、commit、push、rebase 或分支切换。`verification-result.json` 引用相对业务工作区基线的最终差异；试点只交付本地修改和验证证据，由用户审查后决定是否提交。
5. evaluator 修改业务代码前必须先生成并运行真实 DSL，保存红灯报告、事件和诊断文件。合格红灯出现前不得写入业务仓库中的任何文件；临时日志、诊断探针、埋点或计划随后回退的修改同样属于违规并使试点无效，现有证据不足时必须以 blocked 停止。红灯必须到达与 Bug 相关的业务断言；工具报告负责索引相邻业务 API 报文和页面断言事实，evaluator 围绕同一临时数据唯一编码形成双层业务证据：编辑前的本地查询响应和页面列表均包含该编码，保存请求命中本地后端且响应成功，保存后查询再次命中本地后端并完成，并在诊断结论中分别记录查询响应和页面表格是否包含该编码。若被 DSL、数据、环境或工具问题阻断，应先修复验证路径，不能据此修改业务代码。
6. 取得红灯后才允许修改业务根因。每次红灯或绿灯运行前，skill 对 `https://127.0.0.1:3006/` 使用 `http_reachable`、`timeout_seconds: 30`、`tls_verify: false`，对 `http://127.0.0.1:62871/_yms/ready` 使用 `semantic_probe`、`timeout_seconds: 180`、`expected_status: 200`、`json_path: status`、`equals: running`。对于本试点的后端修改，必须先通过 IDEA MCP 重启 `YMS Backend App`，再通过语义就绪检查；这些检查不替代后续相关请求实际命中本地转发目标的证据。
7. evaluator 使用红灯时的同一 DSL 和两组新的验证用临时数据连续获得两次绿色结果，再清理临时数据。任一次绿色运行使用红灯遗留数据、复用前一次数据，或不能证明相关保存和查询请求实际命中预期本地转发目标，都不满足验收门槛。
8. 红灯、第一次绿灯和第二次绿灯分别使用不可复用的运行证据目录。验收保留验证清单、evaluator 事件流、三个目录、DSL、业务代码差异及 evaluator 的诊断结论，并用事件流审计业务修改发生在红灯之后、服务重启和三次验证顺序，以及 evaluator 未修改冻结验证器。验收完成前不自动删除诊断文件。OpenSpec 和工具文档不得提前写入试点 Bug 的具体根因。

skill 在试点结束时使用临时文件加原子替换写入 `verification-result.json`。该文件以 `status: verified|not_verified|invalid` 表达最终状态，并按红灯、第一次绿灯和第二次绿灯记录证据目录、工具 outcome、报告路径、业务断言回执、skill 最终选定的相关 `request_id`、API 与 UI 是否包含临时业务标识、相关请求是否命中本地转发目标、两次绿色数据是否不同、清理结果和验证器指纹复核。未验证或无效时记录原因码及证据引用。`evaluator-final.md` 继续承载人类可读诊断；`verification-manifest.json` 只记录输入、基线和指纹，不混入最终结论。

临时数据清理是 `verified` 的硬门禁。两次绿色业务断言已经通过但清理失败时，最终状态仍为 `not_verified`，原因使用 `cleanup_failed`，并同时记录 `business_assertions_passed: true`、未清理的唯一业务标识、最后已知状态和清理证据，避免误解为业务修复验证失败。skill 只执行一次幂等清理重试并再次查询确认；仍失败即停止，不无限重试。只有两次绿色证据、全部临时数据清理和验证器指纹复核均通过时，才写入 `verified`。
