## ADDED Requirements

### Requirement: 环境配置提供独立 BPR 下载凭据
ydf-browser SHALL 从所选环境的可选 `bpr.username` 和 `bpr.password` 读取 BPR 报告下载凭据，并将其与业务用户凭据完全分离。

环境配置 MUST NOT 提供 BPR 报告地址；登录 origin 和下载页面地址只能来自经过安全校验的 `bpr.stop` 返回 `report_url`。

#### Scenario: BPR 凭据完整配置
- **WHEN** 合并后的所选环境同时包含非空 `bpr.username` 和 `bpr.password`
- **THEN** 配置加载 MUST 接受这组 BPR 凭据
- **AND** BPR 报告下载 MUST 使用该组凭据
- **AND** 业务登录 MUST 继续使用既有业务用户解析结果

#### Scenario: BPR 凭据均未配置
- **WHEN** 合并后的所选环境没有非空 `bpr.username` 和 `bpr.password`
- **THEN** 配置加载 MUST 允许业务运行继续
- **AND** 系统 MUST 将 BPR 下载能力视为未配置

#### Scenario: BPR 凭据只配置一项
- **WHEN** 环境的 `bpr.username` 和 `bpr.password` 只有一项非空
- **THEN** 配置加载 MUST 在启动浏览器前失败
- **AND** 错误消息 MUST 说明 BPR 用户名和密码必须成对配置

#### Scenario: BPR 凭据不回退到业务用户
- **WHEN** 环境未配置完整 BPR 凭据但配置了业务用户凭据
- **THEN** 系统 MUST NOT 使用环境级业务凭据或 `users` 别名凭据下载 BPR 报告

#### Scenario: BPR 秘密不进入运行产物
- **WHEN** 配置加载或 BPR 后处理使用 BPR 凭据
- **THEN** BPR 用户名和密码 MUST NOT 进入 DSL、报告、性能工作簿、事件、错误文本或文件名
- **AND** 提交到版本控制的配置示例 MUST 只包含占位值
