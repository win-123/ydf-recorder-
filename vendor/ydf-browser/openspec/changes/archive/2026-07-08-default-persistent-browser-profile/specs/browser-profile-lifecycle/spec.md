## ADDED Requirements

### Requirement: 默认持久化浏览器 profile
真实浏览器运行时，系统 SHALL 默认使用 ydf-browser 管理的全局唯一持久化浏览器 profile。默认 profile 不按 `base_url`、用户、租户、默认组织或业务年度隔离。

#### Scenario: 默认真实运行使用持久化 profile
- **WHEN** 用户运行 `ydf-browser run --dsl suite.yaml --headless` 且未指定 `--no-persistent-profile`
- **THEN** 系统 SHALL 使用持久化浏览器 profile 执行真实浏览器用例
- **AND** profile 路径 SHALL 默认为 `<YDF_BROWSER_HOME>/browser-profile/default`

#### Scenario: 环境变量覆盖 profile 路径
- **WHEN** 用户设置 `YDF_BROWSER_PROFILE_DIR=/tmp/ydf-profile` 后运行真实浏览器用例
- **THEN** 系统 SHALL 使用该目录作为持久化浏览器 profile
- **AND** 报告中的 profile path SHALL 记录该覆盖路径

#### Scenario: 多环境共享默认 profile
- **WHEN** 用户先后针对不同 `base_url` 运行真实浏览器用例
- **THEN** 系统 SHALL 默认复用同一个持久化浏览器 profile
- **AND** 系统 SHALL NOT 因 `base_url` 不同自动创建环境专属 profile

### Requirement: 临时浏览器上下文回退
系统 SHALL 提供 `--no-persistent-profile` 让真实浏览器运行回到每个用例使用临时浏览器上下文的隔离语义。

#### Scenario: 使用临时浏览器上下文
- **WHEN** 用户运行 `ydf-browser run --dsl suite.yaml --no-persistent-profile`
- **THEN** 系统 SHALL 为每个真实用例创建不持久化的临时浏览器上下文
- **AND** 用例结束后 SHALL 关闭该临时浏览器上下文

#### Scenario: 隔离模式不写默认 profile
- **WHEN** 用户使用 `--no-persistent-profile` 执行真实浏览器用例
- **THEN** 系统 SHALL NOT 写入默认持久化浏览器 profile 目录

### Requirement: 持久化 profile 串行执行
系统 MUST 在持久化浏览器 profile 模式下拒绝并发执行多个用例。

#### Scenario: 持久化模式拒绝并发
- **WHEN** 用户运行 `ydf-browser run --dsl suite.yaml --concurrency 2` 且未指定 `--no-persistent-profile`
- **THEN** 系统 MUST 在执行用例前失败
- **AND** 错误信息 MUST 说明持久化浏览器 profile 模式不支持并发

#### Scenario: 临时模式保留并发能力
- **WHEN** 用户运行 `ydf-browser run --dsl suite.yaml --no-persistent-profile --concurrency 2`
- **THEN** 系统 SHALL 按现有并发调度语义执行

### Requirement: 登录前清当前目标环境可见 cookies
持久化浏览器 profile 模式下，每个真实用例在 API 登录前 MUST 清除当前目标环境可见 cookies，并 SHALL 保留 localStorage、sessionStorage、IndexedDB、HTTP cache 和 service worker。

#### Scenario: API 登录前清理可见 cookies
- **WHEN** 真实用例将使用 `https://dv5-ydf.yonyougov.top` 作为当前 `base_url`
- **THEN** 系统 MUST 在 API 登录前清除浏览器 profile 中对该 host 可见的 cookies
- **AND** 对该 host 可见的父域 cookies MUST 被清除

#### Scenario: 保留前端缓存和 storage
- **WHEN** 系统清除当前目标环境可见 cookies
- **THEN** 系统 SHALL NOT 清除 localStorage、sessionStorage、IndexedDB、HTTP cache 或 service worker

#### Scenario: API 登录仍是事实登录链路
- **WHEN** cookies 清理完成
- **THEN** 系统 SHALL 继续执行 API 登录、切租户、设置默认组织、必要时重新登录、校验用户上下文、切业务年度和菜单解析
- **AND** 系统 SHALL 将最终 API session cookies 注入浏览器后再打开菜单

### Requirement: 页面生命周期隔离
持久化浏览器 profile 模式下，一次 `run` SHALL 复用同一个 browser/profile，但每次 `open_menu` MUST 使用新的 page，并关闭旧 page；每个用例结束后 MUST 关闭本轮运行打开的所有 pages。

#### Scenario: 每次 open_menu 使用新 page
- **WHEN** 同一用例中第二次执行 `open_menu`
- **THEN** 系统 MUST 关闭前一次 `open_menu` 使用的 page
- **AND** 系统 MUST 创建新 page 打开新的菜单

#### Scenario: 用例结束关闭 pages
- **WHEN** 一个真实用例执行结束
- **THEN** 系统 MUST 关闭该用例中由 ydf-browser 打开的所有 pages
- **AND** 系统 SHALL 保留当前 run 的 browser/context/profile 供后续用例继续使用

### Requirement: 清空持久化浏览器 profile
系统 SHALL 提供 `ydf-browser profile clear` 命令清空 ydf-browser 管理的整个持久化浏览器 profile。

#### Scenario: 清空默认 profile
- **WHEN** 用户运行 `ydf-browser profile clear`
- **THEN** 系统 SHALL 删除 ydf-browser 管理的默认持久化浏览器 profile 目录
- **AND** 下一次默认真实运行 SHALL 自动重建该 profile

#### Scenario: profile 正在使用时拒绝清空
- **WHEN** 持久化浏览器 profile 正被运行中的 browser 使用或检测为锁定
- **THEN** `ydf-browser profile clear` MUST 失败
- **AND** 错误信息 MUST 提示先结束正在使用该 profile 的运行

#### Scenario: 不提供细粒度清理
- **WHEN** 用户需要清理持久化浏览器状态
- **THEN** 系统 SHALL 只提供整 profile 清理语义
- **AND** 系统 SHALL NOT 在本能力中提供只清 cookies、只清 storage 或只清 HTTP cache 的命令

### Requirement: profile 信息进入报告
系统 SHALL 在真实运行报告中记录 profile 模式、profile 路径和 cookies reset 策略，但 MUST NOT 记录 cookie 内容、storage 内容或缓存明细。

#### Scenario: 持久化模式报告 profile 信息
- **WHEN** 用例在默认持久化浏览器 profile 模式下执行
- **THEN** 报告 SHALL 包含 `profile.mode` 为 `persistent`
- **AND** 报告 SHALL 包含 profile 路径
- **AND** 报告 SHALL 包含 `profile.cookies_reset` 为 `visible_to_base_url`

#### Scenario: 临时模式报告 profile 信息
- **WHEN** 用例在 `--no-persistent-profile` 模式下执行
- **THEN** 报告 SHALL 包含 `profile.mode` 为 `ephemeral`
- **AND** 报告 SHALL 将 profile 路径记录为空值
- **AND** 报告 SHALL 包含 `profile.cookies_reset` 为 `not_applicable`

#### Scenario: 报告不泄露浏览器状态内容
- **WHEN** 系统生成报告
- **THEN** 报告 MUST NOT 包含 cookie 值
- **AND** 报告 MUST NOT 包含 localStorage、sessionStorage、IndexedDB 或 HTTP cache 的原始内容

### Requirement: fixture 和 validate 不受 profile 影响
fixture 模式和 DSL 校验 SHALL 不启动、不读取、不写入持久化浏览器 profile。

#### Scenario: fixture 模式不使用 profile
- **WHEN** 用户使用 `--template-file` 和 `--runtime-file` 运行 fixture 用例
- **THEN** 系统 SHALL 使用 fixture runtime
- **AND** 系统 SHALL NOT 创建、清理或写入持久化浏览器 profile

#### Scenario: validate 不使用 profile
- **WHEN** 用户运行 `ydf-browser validate --dsl suite.yaml`
- **THEN** 系统 SHALL 只校验 DSL 结构
- **AND** 系统 SHALL NOT 创建、清理或写入持久化浏览器 profile
