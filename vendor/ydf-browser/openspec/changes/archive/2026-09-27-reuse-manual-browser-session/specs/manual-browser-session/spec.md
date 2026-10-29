## ADDED Requirements

### Requirement: 手工会话复用认证并安全收尾
系统 SHALL 在手工会话中复用经身份与工作台探测通过的认证，支持 --force-login，并在整个手工操作期间持有身份锁。系统 MUST 保留当前租户、组织和年度，不主动指定新的业务上下文。

#### Scenario: 关闭后立即重开
- **WHEN** 同一实际环境和账号关闭浏览器后再次启动手工会话，已有认证仍有效
- **THEN** 系统 SHALL 复用认证，不重新提交密码或发送短信

#### Scenario: 显式重新登录
- **WHEN** 手工会话指定 --force-login
- **THEN** 系统 SHALL 忽略已有缓存并执行一次新的凭据认证

#### Scenario: 浏览器关闭后的快照
- **WHEN** 用户关闭浏览器，cookies 已无法读取
- **THEN** 系统 SHALL 保存手工操作期间最后可读取的认证快照，正常返回 browser_closed
- **AND** 系统 MUST NOT 将读取失败当作 cookies 已全部删除；下次使用前必须探测

#### Scenario: 手工变更登录状态
- **WHEN** 手工操作更新或删除 cookies，浏览器仍可读取状态
- **THEN** 系统 SHALL 将差量反映到认证快照，避免恢复已观察到的旧值

#### Scenario: 探测无法判定
- **WHEN** 会话探测发生网络或服务端错误
- **THEN** 系统 MUST 报告失败，不因此重新提交凭据
