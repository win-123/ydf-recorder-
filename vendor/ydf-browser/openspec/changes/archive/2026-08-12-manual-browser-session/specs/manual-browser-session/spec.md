## Purpose

为开发人员提供一个不依赖 DSL 的可见浏览器会话，用于在保持 API 登录和本地请求转发的前提下手工验证本地代码，并明确会话、退出和输出边界。

## ADDED Requirements

### Requirement: 无 DSL 输入时进入手工浏览器会话

系统 SHALL 仅在命令既未提供 `--dsl` 也未提供 `--dsl-list` 时进入手工浏览器会话模式。

#### Scenario: 无 DSL 输入时运行

- **WHEN** 用户运行 `ydf-browser run`，且未提供 `--dsl` 或 `--dsl-list`
- **THEN** 系统 SHALL 进入手工浏览器会话模式
- **AND** 系统 SHALL NOT 加载、解析或执行 DSL 测试集和用例

#### Scenario: 无效 DSL 清单仍按 DSL 输入错误处理

- **WHEN** 用户提供 `--dsl-list`，但清单为空、只包含注释，或包含无效路径
- **THEN** 系统 SHALL 按 DSL 输入错误处理
- **AND** 系统 SHALL NOT 进入手工浏览器会话模式

### Requirement: 校验手工会话参数

手工浏览器会话 SHALL 只接受环境配置、可见浏览器、profile 和请求转发相关参数；没有 DSL 语义的参数 MUST 在启动浏览器前失败。

#### Scenario: 拒绝无头模式

- **WHEN** 无 DSL 的 `run` 同时提供 `--headless`
- **THEN** 系统 MUST 在启动浏览器前失败
- **AND** 错误信息 MUST 说明手工浏览器会话需要可见浏览器

#### Scenario: 拒绝 DSL 和报告参数

- **WHEN** 无 DSL 的 `run` 提供 DSL 过滤、变量、fixture、菜单、报告、性能或 AI 观察参数
- **THEN** 系统 MUST 在启动浏览器前失败
- **AND** 系统 MUST 不创建手工会话报告文件

#### Scenario: 接受转发和 profile 参数

- **WHEN** 无 DSL 的 `run` 提供 `--forward`、`--forward-strip-prefix` 或 `--no-persistent-profile`
- **THEN** 系统 SHALL 保留这些参数的既有语义
- **AND** 系统 SHALL 继续允许不提供任何请求转发规则

### Requirement: 启动已登录的手工浏览器会话

手工浏览器会话 SHALL 使用选定环境的环境级凭据完成现有 API 登录，打开已解析 `base_url` 的根地址，并在浏览器中保持请求转发能力。手工会话 SHALL 不自动切换租户、默认组织或业务年度。

#### Scenario: 成功启动后打开环境首页

- **WHEN** 环境配置有效且 API 登录成功
- **THEN** 系统 SHALL 启动可见浏览器
- **AND** 系统 SHALL 将登录后的 API session cookies 注入浏览器
- **AND** 系统 SHALL 打开已解析环境的 `base_url/`

#### Scenario: 持久化上下文复用初始标签页

- **WHEN** 持久化浏览器上下文启动时已包含初始标签页
- **THEN** 系统 SHALL 在该标签页打开环境首页
- **AND** 系统 SHALL NOT 因启动手工会话而额外保留空白标签页

#### Scenario: 手工操作期间保持请求转发

- **WHEN** 手工会话提供请求转发规则
- **THEN** 浏览器在首页及用户后来打开的页面中 SHALL 继续使用这些规则
- **AND** 系统 SHALL 不要求 DSL 用例才能启用请求转发

#### Scenario: 新标签访问非转发地址不阻塞会话网络

- **WHEN** 手工会话提供请求转发规则，且用户在新标签页访问不匹配转发规则的地址
- **THEN** 系统 SHALL 放行该请求
- **AND** 系统 SHALL 保持原系统页签后续网络请求可继续完成

#### Scenario: 保留环境上下文供手工操作

- **WHEN** 手工会话完成 API 登录并打开首页
- **THEN** 系统 SHALL 保持用户可以在页面中自行选择租户、默认组织和业务年度
- **AND** 系统 SHALL NOT 以缺少 DSL 测试集上下文为启动失败

### Requirement: 手工会话由用户控制生命周期

手工浏览器会话 SHALL 在 browser context 中仍有任意页面时保持 CLI 进程运行，并 SHALL 将用户创建的新标签页视为同一会话的一部分。

#### Scenario: 用户创建的标签页保持会话

- **WHEN** 用户在首页之外打开一个或多个新标签页
- **THEN** 系统 SHALL 继续保持 CLI 进程和请求转发
- **AND** 系统 SHALL 直到 browser context 中没有页面才结束会话

#### Scenario: 关闭全部页面后正常结束

- **WHEN** 首页已成功打开且用户关闭 browser context 中的全部页面
- **THEN** 系统 SHALL 结束手工浏览器会话
- **AND** 系统 SHALL 返回退出码 `0`

#### Scenario: Ctrl-C 中断会话

- **WHEN** 用户在手工会话保持期间按下 `Ctrl-C`
- **THEN** 系统 SHALL 清理已启动的浏览器运行时
- **AND** 系统 SHALL 返回退出码 `130`
- **AND** 系统 SHALL 不将用户中断报告为成功

### Requirement: 手工会话输出与 DSL 报告分离

手工浏览器会话 SHALL 使用独立的最小输出语义，不得把手工操作伪造为 DSL 执行证据。

#### Scenario: 正常关闭输出最小结果

- **WHEN** 手工会话因用户关闭全部页面而正常结束
- **THEN** stdout SHALL 输出包含 `success: true`、`mode: manual_browser_session` 和 `exit_reason: browser_closed` 的 JSON
- **AND** 系统 SHALL 不生成 `report.json` 或 `report.html`

#### Scenario: 启动失败使用非零错误语义

- **WHEN** API 登录、浏览器启动、Cookie 注入或首页导航在会话成功启动前失败
- **THEN** 系统 SHALL 清理已启动的浏览器运行时
- **AND** 系统 SHALL 返回非零退出码
- **AND** 系统 SHALL 不生成 DSL 执行报告

#### Scenario: 手工转发不创建新的证据产物

- **WHEN** 手工会话期间发生请求转发
- **THEN** 系统 SHALL 保持请求转发能力
- **AND** 系统 SHALL 不新增手工会话专用的转发事件或报告文件格式
