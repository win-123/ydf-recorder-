## Context

参见 `proposal.md` 的 `## Why`。当前真实用例在 `WorkflowExecutor.run()` 返回 `ExecutionReport` 后立即进入 `_run_real_case()` 的 `finally`：持久化运行关闭本用例 pages，临时运行停止 browser/context；完整报告则在整个 suite 调度返回后才写入。失败现场暂停必须位于执行器返回与该 `finally` 清理之间，才能同时读取最终步骤结果并保留活页面。

现有 `--on-case-failure` 只控制调度，不控制浏览器清理；`--ai-observe` 使用受超时监督的子进程；`--performance` 可能在用例失败后重新打开菜单。这些路径不能共享交互暂停语义。

## Goals / Non-Goals

**Goals:**

- 默认路径零行为变化，只在显式参数下延后失败页面清理。
- 在单一失败现场中提供稳定的 Enter/主动关闭收尾、Ctrl-C 紧急终止和可解释的报告计时。
- 复用现有报告、失败证据、调度和 `finally` 清理边界。

**Non-Goals:**

- 不提供超时、自动恢复、继续执行、远程控制或浏览器进程脱离 CLI 的能力。
- 不把人工操作采集为 DSL 步骤或验证证据。
- 不支持 fixture、headless、并发、AI 观察或性能采集。
- 不新增 DSL 字段、依赖、持久后台服务或独立暂停子系统。

## Decisions

### 1. 在浏览器启动前集中校验参数

`run` parser 在“用例筛选与执行”组增加 `--pause-on-failure`。`_cmd_run()` 在配置加载和浏览器启动前集中拒绝无 DSL 手工会话、fixture、headless、并发大于 `1`、AI 观察、性能采集、非交互式 stdin，以及显式的 `continue` 或 `stop_suite` 命令行失败策略。

启用参数后，所有已加载 suite 的有效失败策略统一为 `stop_run`；DSL 内的 `on_case_failure` 不再决定本次运行是否继续。显式 `--on-case-failure stop_run` 允许保留，冲突的显式命令行意图则 fail closed。相比让暂停与原调度策略组合，这能保证只有一个失败现场。

### 2. 在执行器返回后、现有清理前等待首个收尾信号

`_run_real_case()` 在执行器返回失败报告后、性能后处理与 `finally` 清理前检查：参数已启用且运行时仍有活 page。`PlaywrightRuntime` 增加最小只读查询 `has_open_page()`，由运行时负责解释 Playwright page 的关闭状态，CLI 不读取其私有字段。由于 `Page.is_closed()` 可能在 browser 进程断连后仍保留本地缓存状态，该查询复用手工会话等待的已有做法：执行无副作用的 `page.evaluate("() => true")` 协议探测，仅将 Playwright 的 target/context/browser closed 异常视为现场已关闭，不把无关页面异常误判为用户收尾。

满足条件时，CLI 先从第一条失败 `StepResult` 提取一基步骤序号、action 和 error，在 stderr 打印用例、步骤、错误、预定报告路径与两种收尾方式。一个守护线程阻塞读取 stdin，主线程以有界轮询检查 Enter 结果和当前失败 page 是否仍打开；Enter、关闭失败页签或关闭整个浏览器中先发生者结束暂停。守护线程只服务本次 CLI 运行，浏览器先关闭时不阻止进程退出。

### 3. 复用原报告与清理所有权

正常收尾后，暂停函数把 `case_code`、`step_index`、`action`、起止时间、等待毫秒数和 `ended_by=enter|browser_closed` 写入现有 `ExecutionReport.timing["failure_pause"]`。随后 `_run_real_case()` 正常返回并进入既有 `finally`；runner 依据 `stop_run` 跳过剩余用例；`_cmd_run()` 沿用现有 JSON、HTML、摘要和非零退出码。主动关闭不是 Ctrl-C 式的外部终止，仍保留完整失败报告；既有清理对“页面、context 或 browser 已关闭”保持幂等，其他清理异常仍正常暴露。

暂停提示只写 stderr，因此不会污染 stdout 的最终 JSON。步骤耗时在进入暂停前已经固定；case/run 外层墙钟计时自然包含人工等待，不新增第二套时钟模型。

### 4. Ctrl-C 保持外部终止语义

stdin 等待抛出的 `KeyboardInterrupt` 先经过 `_run_real_case()` 和外层的现有 `finally`，确保页面、context 和 Playwright 被清理；`_cmd_run()` 仅在启用失败现场暂停时把它转换为退出码 `130` 和最小中断结果。该路径不强行拼装尚未完成的 suite/report，避免把部分结果伪装成完整报告。

## Risks / Trade-offs

- [用户等待时间进入 case/run 总耗时] → 在 `failure_pause.duration_ms` 中显式记录，性能模式直接拒绝，步骤耗时保持原值。
- [用户人工操作改变页面] → 失败证据在暂停前捕获，人工操作不追加到报告，最终结果保持失败。
- [浏览器先关闭时 stdin 守护线程仍可能阻塞] → 该线程不持有浏览器资源且不阻止 CLI 进程退出，不为它增加跨平台终止机制。
- [持久化 profile 长时间保持登录上下文] → 能力必须显式启用且要求交互终端；用户结束检查后仍走现有强制清理。

## Migration Plan

该参数默认关闭，不需要数据迁移。发布后旧命令保持原行为；回滚时移除参数和暂停分支即可，浏览器生命周期仍由原 `finally` 负责。
