# bpr-step-recording Specification

## Purpose
定义 `ydf-browser` 中 BPR 局部录制 DSL、`--performance` 开关语义、运行时接入方式以及报告和性能工作簿中的 BPR 元数据输出要求。

## Requirements
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

### Requirement: BPR sessions 在业务运行后统一下载
系统 SHALL 在业务 DSL 全部执行完成后、生成性能工作簿前，使用所选环境的独立 BPR 凭据在一个隔离浏览器上下文中登录一次，并顺序后处理本次运行的 BPR sessions。

系统 MUST 先检查每个 session 的 `report_url`，再根据独立 BPR 凭据是否完整决定是否下载。

#### Scenario: 报告链接是认证和下载地址的唯一来源
- **WHEN** `bpr.stop` 返回一个无 userinfo 的绝对 HTTPS `report_url`
- **THEN** 系统 MUST 只从该链接提取报告 origin 作为独立 BPR 登录目标
- **AND** 系统 MUST 使用未改写的 `report_url` 作为该 session 的下载页面地址
- **AND** 配置 MUST NOT 增加或回退 BPR 地址字段

#### Scenario: 非法报告链接不接触凭据
- **WHEN** `report_url` 不是绝对 HTTPS URL 或包含 userinfo
- **THEN** session MUST 记录 `download_status=failed` 和安全错误摘要
- **AND** 系统 MUST NOT 向该 URL 或其 origin 提交 BPR 凭据

#### Scenario: 使用报告入口发现实际 CAS 登录页
- **WHEN** 首个合格 `report_url` 跳转到同一 HTTPS origin 的 CAS 登录页
- **THEN** 系统 MUST 使用同一 HTTP session 向该实际登录页提交独立 BPR 凭据
- **AND** 系统 MUST NOT 使用业务登录的固定 `/login_light` service 替代该登录页
- **AND** 登录完成后的下载页面地址仍 MUST 使用未改写的原始 `report_url`

#### Scenario: 报告入口跳转到其它 origin
- **WHEN** 首个合格 `report_url` 的最终登录页不属于报告 origin
- **THEN** 系统 MUST 在解析表单或提交凭据前安全失败
- **AND** 系统 MUST NOT 向该登录页提交 BPR 用户名或密码

#### Scenario: 一次运行只接受一个报告 origin
- **WHEN** 一次运行中的合格 sessions 包含不同的报告 origin
- **THEN** 系统 MUST 只使用第一个合格 session 的 origin 建立一次登录会话和一个隔离浏览器上下文
- **AND** 其它 origin 的 sessions MUST 安全失败
- **AND** 系统 MUST NOT 向其它 origin 提交 BPR 凭据

#### Scenario: 多段 BPR 共用一次独立登录
- **WHEN** 一次性能运行产生多个带在线报告链接的 BPR sessions 且已配置完整 BPR 凭据
- **THEN** 系统 MUST 只建立一次 BPR 登录会话和一个隔离浏览器上下文
- **AND** 系统 MUST 在该上下文中顺序处理全部 sessions
- **AND** 系统 MUST NOT 回退复用业务用户登录态

#### Scenario: BPR 下载使用单一总期限
- **WHEN** 系统开始打开某个 session 的 BPR 在线报告链接
- **THEN** 系统 MUST 使用单调时钟建立从开始打开报告到 download 事件完成不超过 60 秒的单一 deadline
- **AND** 页面打开、BPR ID 匹配、下载按钮可用和 download 事件完成 MUST 共用该 deadline 的剩余预算
- **AND** 任一阶段 MUST NOT 重置或延长该 60 秒总预算
- **AND** 只有页面中的 BPR ID 与 session 一致且下载按钮可见可用后系统才可点击下载按钮

#### Scenario: URL 报告记录键与 session BPR ID 不同
- **WHEN** `report_url` 的 `pk` 与 session BPR ID 不同，但加载后 `window.pageData?.bprBaseInfo?.bprId` 与 session 一致
- **THEN** 系统 MUST 允许通过真实 download 事件下载报告
- **AND** 系统 MUST NOT 把 URL `pk` 当作 session BPR ID

#### Scenario: BPR 报告通过真实下载事件保存
- **WHEN** BPR 页面已匹配当前 session 且下载按钮可用
- **THEN** 系统 MUST 捕获浏览器 download 事件并点击页面的真实下载按钮
- **AND** 没有捕获 download 事件时系统 MUST NOT 报告下载成功

#### Scenario: BPR 下载失败不改变业务结果
- **WHEN** 业务用例已经完成但 BPR 登录、等待或下载失败
- **THEN** session MUST 记录 `download_status=failed` 和安全错误摘要
- **AND** 系统 MUST NOT 改变业务用例状态、运行 success 或 CLI 退出码
- **AND** 系统 MUST 保留已取得的在线报告链接和其它 session 已下载的原始文件

#### Scenario: 失败 session 没有在线报告链接
- **WHEN** 业务运行完成后一个既有失败 BPR session 没有 `report_url`
- **THEN** session MUST 记录 `download_status=failed` 和安全错误摘要
- **AND** `summary_status` MUST 为 `not_attempted`
- **AND** 即使独立 BPR 凭据未配置，系统也 MUST NOT 将该 session 标记为 `not_configured`
- **AND** 系统 MUST NOT 尝试打开空 URL 或执行下载
- **AND** 系统 MUST NOT 改变业务用例状态、运行 success 或 CLI 退出码

#### Scenario: 未配置 BPR 凭据
- **WHEN** 业务运行产生一个有 `report_url` 的 BPR session 但所选环境未配置 BPR 用户名和密码
- **THEN** 该 session MUST 记录 `download_status=not_configured`
- **AND** `summary_status` MUST 为 `not_attempted`
- **AND** 系统 MUST NOT 改变业务用例状态、运行 success 或 CLI 退出码

### Requirement: 原始 BPR 报告作为敏感产物保存
系统 SHALL 按下载原文保存 BPR HTML，并以 session 可追溯、仅当前用户可读写的方式纳入报告目录。

#### Scenario: 保存原始 BPR 文件
- **WHEN** 第 `index` 个 session 的 BPR ID 为 `bpr_id` 且下载成功
- **THEN** 系统 MUST 将文件保存到 `artifacts/<suite>/<case>/bpr/<index>-<bpr_id>.html`
- **AND** 系统 MUST 先在报告目录内权限为 `0700` 的私有临时目录接收下载文件，设置文件权限为 `0600` 后再原子移动到最终路径
- **AND** 下载保存失败时系统 MUST 清理私有临时目录且 MUST NOT 产生最终文件
- **AND** 文件权限 MUST 为 `0600`
- **AND** `download_status` MUST 为 `downloaded`

#### Scenario: 原始文件保持不改写
- **WHEN** BPR HTML 已下载
- **THEN** 系统 MUST 保留下载原文而不改写文件内容
- **AND** 后续概要解析失败 MUST NOT 删除该文件或把下载状态改为失败

#### Scenario: BPR 文件路径进入报告
- **WHEN** 原始 BPR 文件已保存
- **THEN** JSON 和 Excel MUST 保存该文件的绝对路径
- **AND** HTML 报告 MUST 使用相对于报告目录的链接
- **AND** BPR 文件 MUST NOT 进入 `diagnostic_files`

#### Scenario: 敏感 BPR 内容不被传播
- **WHEN** 系统处理原始 BPR 文件
- **THEN** 系统 MUST NOT 在事件、错误文本、控制台、性能工作簿、`report.json` 或 `report.html` 中输出原始 BPR HTML 全文、源码或固定 14 项概要之外的任意 HTML 片段
- **AND** 按固定 14 项字段映射提取的用户可见概要 MUST 允许作为结构化 `server_summary` 和对应工作簿列输出，且 MUST NOT 被视为原文泄漏
- **AND** 系统 MUST NOT 将原始文件描述为已脱敏产物

### Requirement: BPR session 记录固定服务端概要
系统 SHALL 从已下载 BPR 报告的用户可见服务端概要中提取固定 14 项值，并分别记录概要数据、状态和安全错误摘要。

#### Scenario: 服务端概要完整
- **WHEN** BPR 报告的 `#summary-posi` 首行包含全部固定字段
- **THEN** session MUST 记录 `summary_status=parsed`
- **AND** `server_summary` MUST 保留 `totalCostTime`、`appCostTime`、`totalRedisCostTime`、`totalSqlCostTime`、`totalReadrResultTime`、`totalThreadNum`、`totalRpcNum`、`totalRuleCostTime`、`readFromClientTime`、`writeToClientTime`、`readFromClient`、`readFromServer`、`notClosedConnecttion` 和 `errorSize` 的用户可见文本

#### Scenario: 服务端概要部分缺失
- **WHEN** BPR 报告至少包含一个固定概要字段但未包含全部 14 项
- **THEN** session MUST 记录 `summary_status=partial`
- **AND** 已取得的值 MUST 保留，缺失字段 MUST 留空
- **AND** 未知字段 MUST 被忽略而不动态增加工作簿列

#### Scenario: 服务端概要无法解析
- **WHEN** BPR 报告找不到服务端概要或解析发生异常
- **THEN** session MUST 记录 `summary_status=failed` 和安全错误摘要
- **AND** 系统 MUST 保留原始文件及 `download_status=downloaded`
- **AND** 系统 MUST NOT 改变业务用例状态、运行 success 或 CLI 退出码

### Requirement: BPR session 元数据同时保留状态链接和时间
系统 SHALL 在 session 和性能工作簿中保留在线报告、本地文件、后处理状态、服务端概要和可追溯时间信息，并在 HTML 报告中保留本地/在线入口和后处理状态。

#### Scenario: session 保存后处理字段
- **WHEN** 系统后处理一个 BPR session
- **THEN** session MUST 保留现有 `report_url`
- **AND** session MUST 包含 `report_file`、`download_status`、`download_error`、`summary_status`、`summary_error` 和 `server_summary`
- **AND** `download_status` MUST 为 `not_configured`、`downloaded` 或 `failed`
- **AND** `summary_status` MUST 为 `not_attempted`、`parsed`、`partial` 或 `failed`

#### Scenario: 工作簿输出可读时间和原始时间戳
- **WHEN** `BPR录制` sheet 输出 session 行
- **THEN** 工作簿 MUST 输出带运行机器本地时区偏移的可读开始和结束时间
- **AND** 工作簿 MUST 同时保留 `开始时间戳(ms)` 和 `结束时间戳(ms)`
- **AND** `report.json` MUST 保留 Unix epoch 毫秒值

#### Scenario: 工作簿输出固定服务端概要列
- **WHEN** `BPR录制` sheet 输出 session 行
- **THEN** 工作簿 MUST 输出本地 BPR 文件、在线报告链接、下载状态、下载错误、概要状态、概要错误和固定 14 项服务端概要列
- **AND** 概要不可用或缺失的值 MUST 留空

#### Scenario: HTML 报告同时提供本地和在线入口
- **WHEN** 一个 BPR session 既有本地报告文件又有在线报告链接
- **THEN** HTML 报告 MUST 同时展示可移动的本地相对链接和在线报告链接

#### Scenario: HTML 报告拒绝不安全的在线入口
- **WHEN** session 的 `report_url` 不是无 userinfo 的绝对 HTTPS URL
- **THEN** HTML 报告 MUST NOT 生成在线链接或展示原始 `report_url`
- **AND** HTML 报告 MUST 继续展示下载和概要后处理状态

#### Scenario: 错误摘要不泄露敏感信息
- **WHEN** BPR 登录、下载或概要解析失败
- **THEN** `download_error` 或 `summary_error` MUST 只保存阶段和安全错误摘要
- **AND** 错误文本 MUST NOT 包含 BPR 用户名、密码、响应正文或 BPR 文件内容
