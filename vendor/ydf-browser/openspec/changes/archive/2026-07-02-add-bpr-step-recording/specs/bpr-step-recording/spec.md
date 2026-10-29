## ADDED Requirements
### Requirement: BPR DSL steps
系统 SHALL 支持在 DSL steps 中使用 `component: bpr` 显式控制局部 BPR 录制，并将 BPR 录制能力纳入 `--performance` 性能采集开关。

#### Scenario: 启动 BPR 录制
- **WHEN** DSL 步骤声明 `component: bpr` 且 `operation: start`
- **AND** 本次运行已开启 `--performance`
- **THEN** 系统 MUST 开始一个新的 BPR session
- **AND** 系统 MUST 记录该 session 的 `start_control_step`
- **AND** `bpr.start` 步骤本身 MUST NOT 计入该 session 的业务录制范围

#### Scenario: 停止 BPR 录制
- **WHEN** DSL 步骤声明 `component: bpr` 且 `operation: stop`
- **AND** 本次运行已开启 `--performance`
- **THEN** 系统 MUST 结束当前 active BPR session
- **AND** 系统 MUST 记录该 session 的 `end_control_step`
- **AND** `bpr.stop` 步骤本身 MUST NOT 计入该 session 的业务录制范围
- **AND** 系统 MUST 保存 BPR 在线报告链接到该 session 元数据

#### Scenario: 未开启性能采集时忽略 BPR 控制步骤
- **WHEN** DSL 步骤声明 `component: bpr`
- **AND** 本次运行未开启 `--performance`
- **THEN** 系统 MUST NOT 调用 BPR start 或 stop runtime 接口
- **AND** 系统 MUST 在执行、步骤结果、事件流、`report.json`、`report.html` 和 `performance.xlsx` 中忽略这些 BPR 控制步骤
- **AND** 系统 MUST NOT 创建 BPR session 元数据
- **AND** 系统 MUST NOT 输出 BPR 跳过记录、BPR 报告区块、BPR sheet 或其他 BPR 运行痕迹

#### Scenario: 同一 case 多段 BPR 录制
- **WHEN** 一个 case 中包含多组 `bpr.start` 和 `bpr.stop`
- **AND** 本次运行已开启 `--performance`
- **THEN** 系统 MUST 为每组 start/stop 生成独立 BPR session
- **AND** 每个 session MUST 保留自己的步骤范围、包含步骤和在线报告链接

### Requirement: BPR state validation
系统 SHALL 在显式 DSL 校验和开启 `--performance` 的运行加载阶段，对每个 case 的 BPR session 配对状态进行显式校验，避免无效 BPR DSL 进入登录和业务执行阶段。

#### Scenario: 拒绝嵌套 BPR 录制
- **WHEN** DSL 加载器在显式校验命令或开启 `--performance` 的运行中校验某个 case 的 steps
- **AND** 已存在未闭合的 `bpr.start` 后又出现另一个 `bpr.start`
- **THEN** DSL 语法校验 MUST 失败
- **AND** 错误消息 MUST 明确说明不支持嵌套 BPR 录制

#### Scenario: 拒绝未启动时停止 BPR
- **WHEN** DSL 加载器在显式校验命令或开启 `--performance` 的运行中校验某个 case 的 steps
- **AND** 当前没有未闭合的 `bpr.start` 却出现 `bpr.stop`
- **THEN** DSL 语法校验 MUST 失败
- **AND** 错误消息 MUST 明确说明没有正在录制的 BPR session

#### Scenario: 拒绝缺少 stop 的录制
- **WHEN** DSL 加载器在显式校验命令或开启 `--performance` 的运行中校验某个 case 的 steps
- **AND** steps 结束时仍存在未闭合的 `bpr.start`
- **THEN** DSL 语法校验 MUST 失败
- **AND** 错误消息 MUST 明确说明缺少 `bpr.stop`

#### Scenario: 非性能运行不因 BPR 配对错误失败
- **WHEN** `ydf-browser run` 加载 DSL
- **AND** 本次运行未开启 `--performance`
- **AND** DSL 中存在嵌套 BPR、无 active session 的 `bpr.stop` 或缺少 `bpr.stop`
- **THEN** 系统 MUST 将 BPR 控制步骤视为禁用的性能指令并忽略
- **AND** 系统 MUST NOT 因这些 BPR 配对状态错误阻断非性能运行
- **AND** 系统 MUST NOT 在任何运行产物中输出 BPR 错误或 BPR 跳过痕迹

#### Scenario: 执行器保留 BPR 状态保护
- **WHEN** 执行器通过测试或其他内部入口接收到未经过 DSL 加载器校验的 BPR steps
- **THEN** 执行器 MUST 仍然拒绝嵌套 BPR、无 active session 的 `bpr.stop` 和 case 结束时未闭合的 BPR session
- **AND** 这些保护 MUST NOT 取代 DSL 加载阶段的静态校验

### Requirement: BPR runtime integration
系统 SHALL 在开启 `--performance` 的真实 Playwright runtime 中通过浏览器上下文接入 BPR 录制接口。

#### Scenario: 启动时写入 BPR cookies
- **WHEN** 执行 `bpr.start`
- **AND** 本次运行已开启 `--performance`
- **THEN** runtime MUST 为当前业务域名写入 `mdd_monitor_uid`、`ymc_flag`、`mdd_monitor_record` 和 `ymc_recording` cookies
- **AND** `ymc_flag` MUST 使用 URL 编码后的 `bprId=<id>;bprStartTs=<startTs>`

#### Scenario: 启动时通知录制接口
- **WHEN** 本次运行已开启 `--performance`
- **AND** BPR cookies 已写入
- **THEN** runtime SHOULD 通过当前页面上下文调用 `/iuap-ymc-agent/monitor/record`
- **AND** 该调用 SHOULD 使用浏览器自动携带的登录态、Referer 和 Origin

#### Scenario: 停止时返回报告链接
- **WHEN** 执行 `bpr.stop`
- **AND** 本次运行已开启 `--performance`
- **THEN** runtime MUST 通过当前页面上下文调用 `/iuap-ymc-agent/bprcall`
- **AND** 请求 MUST 提交包含 `ubaData` 的 JSON 请求体
- **AND** 响应 MUST 提供 HTTP 在线报告链接，否则 stop 步骤 MUST 失败

### Requirement: BPR report metadata
系统 SHALL 在运行报告中输出 BPR session 元数据，以供外部分析程序消费。

#### Scenario: case report 存储 BPR sessions
- **WHEN** 一个 case 生成了一个或多个 BPR session
- **AND** 本次运行已开启 `--performance`
- **THEN** case report MUST 包含 `bpr_sessions`
- **AND** 每个 session MUST 包含 BPR 序号、BPR ID、控制步骤、业务步骤范围、包含步骤、在线报告链接、状态和错误信息

#### Scenario: 业务范围排除控制步骤
- **WHEN** 一个 session 由 `bpr.start`、若干业务步骤和 `bpr.stop` 组成
- **THEN** session 的 `start_step` MUST 指向第一条被录制业务步骤
- **AND** session 的 `end_step` MUST 指向最后一条被录制业务步骤
- **AND** session 的 `actions` MUST NOT 包含 `bpr.start` 或 `bpr.stop`

#### Scenario: HTML 报告展示 BPR 链接
- **WHEN** case report 包含 BPR sessions
- **THEN** HTML 报告 MUST 展示每个 session 的录制范围和在线报告链接

### Requirement: BPR sessions 导出到性能工作簿
系统 SHALL 在性能工作簿中提供 BPR 录制清单，供外部分析程序关联 DSL 步骤范围与 BPR 在线报告。

#### Scenario: 工作簿包含 BPR sheet
- **WHEN** 一次开启 `--performance` 的运行生成 `performance.xlsx`
- **THEN** 工作簿 MUST 包含 `BPR录制` sheet
- **AND** 该 sheet MUST 为每个 BPR session 输出一行记录

#### Scenario: BPR sheet 包含分析输入
- **WHEN** `BPR录制` sheet 输出 session 行
- **THEN** 每行 MUST 包含运行 ID、suite code、case code、BPR 序号、BPR 名称、BPR ID、控制步骤、业务步骤范围、包含步骤和 BPR 在线报告链接
- **AND** 每行 SHOULD 包含开始时间、结束时间、耗时、状态和错误信息

#### Scenario: 工作簿处理无 BPR 录制
- **WHEN** 一次开启 `--performance` 的运行没有产生 BPR session
- **THEN** `BPR录制` sheet MUST 仍然存在
- **AND** 该 sheet MUST 清晰标记没有 BPR 录制记录

#### Scenario: 未开启性能采集时不因 BPR 生成工作簿
- **WHEN** 一次运行未开启 `--performance`
- **AND** DSL 中包含 `bpr.start` / `bpr.stop`
- **THEN** 系统 MUST NOT 因 BPR 步骤单独生成 `performance.xlsx`
- **AND** 如果本次运行因为其他原因生成运行产物，这些产物 MUST NOT 包含 BPR session、BPR step result、BPR 跳过记录或 BPR sheet
