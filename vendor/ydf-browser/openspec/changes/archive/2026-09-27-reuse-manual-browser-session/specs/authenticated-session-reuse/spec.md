## MODIFIED Requirements

### Requirement: 按实际账号身份复用会话
系统 SHALL 在真实 DSL 运行和无 DSL 手工浏览器会话中默认按规范化后的 `base_url + username` 跨用例、跨命令运行复用会话，且 MUST 独立于浏览器 profile 模式处理认证复用。

#### Scenario: 别名不同但实际身份相同
- **WHEN** 两个用例使用不同配置别名但实际环境地址和用户名相同，已有会话有效
- **THEN** 系统 SHALL 复用同一身份的会话且不重新提交密码

#### Scenario: 不同身份隔离
- **WHEN** 环境地址或用户名不同
- **THEN** 系统 MUST NOT 将另一身份的会话作为当前账号直接执行业务

#### Scenario: 临时浏览器也复用认证
- **WHEN** 用户使用 `--no-persistent-profile` 且缓存会话有效
- **THEN** 系统 SHALL 为新浏览器上下文安装有效会话而不重新提交密码
