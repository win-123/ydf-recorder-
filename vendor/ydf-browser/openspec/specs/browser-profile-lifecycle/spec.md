# browser-profile-lifecycle Specification

## Purpose
定义真实浏览器运行中 ydf-browser 管理的浏览器 profile 生命周期、登录前 cookies 处理、页面隔离、清空命令和报告字段。

## Requirements

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
系统 SHALL 提供 `--no-persistent-profile` 让真实运行使用每个用例独立的临时浏览器上下文；该选项 MUST NOT 隐含强制重新认证。

#### Scenario: 使用临时浏览器上下文
- **WHEN** 用户运行 `ydf-browser run --dsl suite.yaml --no-persistent-profile`
- **THEN** 系统 SHALL 为每个真实用例创建不持久化的临时浏览器上下文
- **AND** 用例结束后 SHALL 关闭该临时浏览器上下文
- **AND** 系统 SHALL 可在独立的认证会话缓存中保存有效会话供下一用例使用

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

### Requirement: 页面生命周期隔离
持久化浏览器 profile 模式下，一次 `run` SHALL 复用同一个 browser/profile；每次 `open_menu` MUST 使用新的业务 page，并关闭旧业务 page；每个用例结束后 MUST 关闭本用例打开的所有业务 page，同时 MUST 保留一个 run-scope page 使当前 context 可供后续用例继续使用。page 交接期间共享 context MUST NOT 进入零 page 状态。

#### Scenario: 每次 open_menu 使用新 page
- **WHEN** 同一用例中第二次执行 `open_menu`
- **THEN** 系统 MUST 先创建新的业务 page，再关闭前一次 `open_menu` 使用的 page
- **AND** 系统 MUST 使用新 page 打开新的菜单
- **AND** 交接期间共享 context MUST 始终至少包含一个可用 page

#### Scenario: 用例结束关闭 pages
- **WHEN** 一个真实用例执行结束
- **THEN** 系统 MUST 先创建一个不承载该用例业务状态的 run-scope page
- **AND** 系统 MUST 关闭该用例中由 ydf-browser 打开的所有业务 pages
- **AND** 系统 SHALL 保留当前 run 的 browser/context/profile 和 run-scope page 供后续用例继续使用

#### Scenario: 下一用例替换 run-scope page
- **WHEN** 后续用例在同一持久化 context 中执行第一个 `open_menu`
- **THEN** 系统 MUST 先创建新的业务 page，再关闭前一用例保留的 run-scope page
- **AND** 系统 MUST NOT 复用前一用例的业务 page 或页面状态

#### Scenario: run 结束关闭共享 context
- **WHEN** 持久化 profile 的整个 `run` 结束
- **THEN** 系统 MUST 关闭共享 context 及其剩余 page

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
系统 SHALL 在真实运行报告中记录 profile 模式、profile 路径和 cookies reset 策略，但 MUST NOT 记录 cookie 内容、storage 内容或缓存明细。认证复用结果 SHALL 与 profile 模式分别报告。

#### Scenario: 持久化模式报告 profile 信息
- **WHEN** 用例在默认持久化浏览器 profile 模式下执行
- **THEN** 报告 SHALL 包含 `profile.mode` 为 `persistent`
- **AND** 报告 SHALL 包含 profile 路径
- **AND** 报告 SHALL 包含 `profile.cookies_reset` 为 `restore_authenticated_session`

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

### Requirement: 用例准备恢复目标身份会话
带 DSL 的真实运行 MUST 在每个用例准备阶段建立经过验证的当前身份会话；持久化 profile 中残留的 cookies MUST NOT 替代账号身份校验。

#### Scenario: 同身份有效会话恢复
- **WHEN** 后续用例使用同一实际账号且保存会话仍然有效
- **THEN** 系统 SHALL 恢复最新会话而不重新提交密码
- **AND** 系统 SHALL 继续保留 localStorage、sessionStorage、IndexedDB、HTTP cache 和 service worker 的既有持久化语义

#### Scenario: 同站点切换账号
- **WHEN** 后续用例使用同站点的另一个账号
- **THEN** 系统 MUST 保存前一身份的最新会话并替换当前目标环境可见 cookies，包括相关父域 cookies
- **AND** 系统 MUST 验证新账号与业务上下文，不得混用旧账号 cookies 或页面上下文
- **AND** 系统 SHALL 保持现有新建业务 page 和关闭旧业务 page 的生命周期
