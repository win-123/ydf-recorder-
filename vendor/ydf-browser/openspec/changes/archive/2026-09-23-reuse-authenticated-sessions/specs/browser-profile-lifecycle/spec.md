## REMOVED Requirements

### Requirement: 登录前清当前目标环境可见 cookies
**Reason**: 每例无条件清除并重新登录与已确认的认证复用策略冲突。
**Migration**: 用例准备时恢复并验证当前身份的会话；账号交接时替换目标 cookies，强制认证通过 `run --force-login` 控制。

## ADDED Requirements

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

## MODIFIED Requirements

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
