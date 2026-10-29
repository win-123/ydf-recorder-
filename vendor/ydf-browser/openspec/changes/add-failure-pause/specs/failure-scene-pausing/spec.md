## Purpose

定义真实 DSL 失败后由用户显式启用的交互式现场暂停能力，使用户能够核对失败当刻的可见页面，同时保持原失败结论、报告证据和浏览器清理边界可解释。

## ADDED Requirements

### Requirement: 失败现场暂停必须显式启用并限制运行模式
系统 SHALL 为 `ydf-browser run` 提供 `--pause-on-failure`，且未启用时 MUST 保持现有执行、失败策略和浏览器清理行为不变。该参数 MUST 只允许用于带 DSL 输入的真实、有头、串行、交互式普通运行，并 SHALL 同时支持持久化 profile 与 `--no-persistent-profile`。

#### Scenario: 有效启用失败现场暂停
- **WHEN** 用户在交互式终端中运行真实 DSL，并指定 `--pause-on-failure`、`--concurrency 1`，且未启用 headless、fixture、AI 观察或性能采集
- **THEN** 系统 SHALL 启用失败现场暂停
- **AND** 系统 SHALL 允许持久化或临时浏览器 profile

#### Scenario: 拒绝不兼容运行模式
- **WHEN** `--pause-on-failure` 与无 DSL 手工会话、`--headless`、fixture、`--concurrency` 大于 `1`、`--ai-observe`、`--performance` 或非交互式 stdin 任一条件同时出现
- **THEN** 系统 MUST 在启动浏览器前失败
- **AND** 错误信息 MUST 指明不兼容条件

#### Scenario: 拒绝冲突的命令行失败策略
- **WHEN** 用户同时指定 `--pause-on-failure` 和显式的 `--on-case-failure continue` 或 `--on-case-failure stop_suite`
- **THEN** 系统 MUST 在启动浏览器前失败
- **AND** 系统 SHALL 允许显式的 `--on-case-failure stop_run`

### Requirement: 仅可检查的 DSL 步骤失败触发暂停
系统 MUST 只在已进入 DSL 步骤执行、用例得到失败报告且浏览器仍有可检查页面时触发失败现场暂停。触发后系统 MUST 停止整次运行，不得继续调度当前或后续测试集中的其他用例；DSL 内的失败继续策略 SHALL 被本次显式暂停运行的 `stop_run` 语义覆盖。

#### Scenario: DSL 步骤失败且页面可检查
- **WHEN** `open_menu`、组件操作、业务断言或工具步骤执行异常使当前用例失败，且失败页面仍可检查
- **THEN** 系统 MUST 保留失败当刻的页面并进入等待
- **AND** 系统 MUST NOT 执行当前用例的剩余步骤或任何后续用例

#### Scenario: 无可检查页面时不暂停
- **WHEN** DSL 加载或校验、环境配置、API 登录、浏览器启动发生失败，或者失败发生时页面或浏览器已经关闭
- **THEN** 系统 MUST NOT 进入失败现场暂停
- **AND** 系统 SHALL 按既有失败清理和报告语义结束

#### Scenario: 外部终止不触发暂停
- **WHEN** 运行在生成可暂停的 DSL 步骤失败报告前因外部终止而结束
- **THEN** 系统 MUST NOT 进入失败现场暂停
- **AND** 终止处理 SHALL 保持既有浏览器关闭和证据收尾语义

### Requirement: 暂停期间保持诊断与执行证据分离
失败现场暂停期间，系统 SHALL 保持失败页面可交互，并 MUST 将暂停提示写入 stderr，不得在最终 JSON 前向 stdout 写入交互提示。用户在页面中的人工操作 SHALL 仅用于诊断，MUST NOT 追加为 DSL 步骤、改变已捕获的失败证据或覆盖原失败结果。

#### Scenario: 暂停提示包含失败上下文
- **WHEN** 系统进入失败现场暂停
- **THEN** stderr SHALL 显示用例、失败步骤、错误、预定报告路径和按 Enter 或关闭失败页面结束检查的提示
- **AND** stdout SHALL 保留给运行结束后的结构化 JSON

#### Scenario: 人工检查不改变失败结论
- **WHEN** 用户在暂停期间查看或操作失败页面
- **THEN** 系统 MUST NOT 把人工操作记录为 DSL 步骤或验证证据
- **AND** 用户结束检查后运行结果 MUST 仍为暂停前的失败结果

### Requirement: Enter、主动关闭与 Ctrl-C 使用可区分的收尾语义
系统 SHALL 在交互式终端中无固定超时地等待用户结束检查。用户按 Enter、关闭失败页签或关闭整个浏览器时，系统 MUST 沿用现有浏览器清理流程、生成完整失败报告并返回原失败退出码；用户按 Ctrl-C 时，系统 MUST 清理浏览器并返回 `130`，但不保证生成完整报告。

#### Scenario: Enter 正常结束检查
- **WHEN** 用户在失败现场暂停期间按 Enter
- **THEN** 系统 MUST 关闭失败用例的页面和浏览器上下文
- **AND** 系统 MUST 生成结构化报告和 HTML 报告
- **AND** 命令 MUST 返回原失败退出码

#### Scenario: 关闭失败页面正常结束检查
- **WHEN** 用户在失败现场暂停期间关闭失败页签或整个浏览器
- **THEN** 系统 MUST 自动结束等待，不再要求用户按 Enter
- **AND** 系统 MUST 生成结构化报告和 HTML 报告
- **AND** 命令 MUST 返回原失败退出码

#### Scenario: Ctrl-C 紧急终止检查
- **WHEN** 用户在失败现场暂停期间按 Ctrl-C
- **THEN** 系统 MUST 清理已启动的浏览器运行时
- **AND** 命令 MUST 返回退出码 `130`
- **AND** 系统 SHALL NOT 承诺生成完整结构化报告或 HTML 报告

### Requirement: 报告必须区分人工暂停与步骤耗时
Enter 或主动关闭正常收尾后的用例报告 MUST 在 `report.timing.failure_pause` 中记录 `case_code`、一基失败步骤序号 `step_index`、`action`、`started_at`、`ended_at`、`duration_ms` 和 `ended_by`；`ended_by` MUST 分别使用 `enter` 或 `browser_closed`。步骤自身的耗时 MUST 保持暂停前已捕获的值，case 与 run 总耗时 SHALL 保持墙钟时间并包含人工等待。

#### Scenario: 暂停记录进入失败报告
- **WHEN** 失败现场暂停由 Enter 或主动关闭正常结束并生成报告
- **THEN** `report.timing.failure_pause` MUST 包含失败位置、起止时间、非负等待毫秒数和对应的 `ended_by`
- **AND** 失败步骤原有的 `data.timing.duration_ms` MUST NOT 包含人工等待
- **AND** case 与 run 的总 `duration_ms` SHALL 包含人工等待
