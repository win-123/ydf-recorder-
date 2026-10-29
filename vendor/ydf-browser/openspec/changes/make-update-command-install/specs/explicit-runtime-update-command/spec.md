## Purpose

为安装版 ydf-browser 提供一个可立即执行的显式 runtime 更新入口，同时保留只读检查、显式回滚和现有分阶段安装的安全边界。

## ADDED Requirements

### Requirement: 默认显式更新

系统 MUST 将用户运行 ydf-browser update 解释为一次绕过 24 小时检查冷却的前台更新操作。系统 MUST 只在受信 stable 清单版本高于当前 runtime 时安装新版本，不得因为该命令重装相同版本或降级。

#### Scenario: 存在更高 stable runtime

- **WHEN** 用户运行 ydf-browser update 且受信清单中的 stable 版本高于当前 runtime
- **THEN** 系统 MUST 前台执行现有 runtime 更新流程
- **AND** 系统 MUST 在下载、摘要校验、安装和健康检查成功后报告 installed
- **AND** 系统 MUST 记录当前版本和已安装版本

#### Scenario: 没有更高 stable runtime

- **WHEN** 用户运行 ydf-browser update 且清单版本不高于当前 runtime
- **THEN** 系统 MUST 报告 no_update
- **AND** 系统 MUST NOT 下载发布包或修改 current
- **AND** 系统 MUST 返回成功退出码

### Requirement: 只读检查与回滚命令矩阵

系统 MUST 保留 ydf-browser update --check 作为绕过冷却但不安装的前台检查，并 MUST 保留 ydf-browser update rollback 作为切换上一保留 runtime 的显式回滚。系统 MUST 拒绝将 --check 与 rollback 组合使用。

#### Scenario: 用户只读检查

- **WHEN** 用户运行 ydf-browser update --check
- **THEN** 系统 MUST 前台读取受信清单并报告当前版本、可用版本或 no_update
- **AND** 系统 MUST NOT 下载发布包
- **AND** 系统 MUST NOT 修改 current

#### Scenario: 用户显式回滚

- **WHEN** 用户运行 ydf-browser update rollback 且存在上一保留 runtime
- **THEN** 系统 MUST 将后续命令的生效指针切换到上一 runtime
- **AND** 系统 MUST 报告 rolled_back 及当前版本

#### Scenario: 冲突的检查与回滚参数

- **WHEN** 用户将 --check 与 rollback 同时传给 update
- **THEN** 系统 MUST 拒绝该命令
- **AND** 系统 MUST 返回非零退出码和可读错误
- **AND** 系统 MUST NOT 修改 current

### Requirement: 手动检查绕过冷却并独立于后台开关

显式 update 和 update --check MUST 绕过后台更新的 24 小时冷却。YDF_BROWSER_AUTO_UPDATE=0 MUST 只禁止后台自动检查和安装，不得禁止用户显式执行上述命令。显式检查或更新完成后 MUST 持久化本次检查时间和结果，使后台检查复用该状态。

#### Scenario: 最近完成过后台检查仍执行手动更新

- **WHEN** update-state 中的最近检查时间距当前时间不足 24 小时且用户运行 ydf-browser update
- **THEN** 系统 MUST 仍然读取清单
- **AND** 系统 MUST 按清单判断是否安装新版本

#### Scenario: 关闭后台更新后执行手动更新

- **WHEN** 用户设置 YDF_BROWSER_AUTO_UPDATE=0 并运行 ydf-browser update
- **THEN** 系统 MUST 执行显式前台更新
- **AND** 系统 MUST NOT 因该环境变量跳过显式操作

#### Scenario: 手动检查更新检查状态

- **WHEN** 显式 update 或 update --check 完成检查或记录失败
- **THEN** 系统 MUST 保存最近检查时间、结果和可用版本等已有更新状态
- **AND** 后续后台检查 MUST 使用该状态判断冷却周期

### Requirement: 失败、锁和结构化退出语义

显式更新 MUST 复用现有安装锁、失败状态和 JSON 输出。安装、完整性或健康检查失败时系统 MUST 保留 current；当已有更新任务持有安装锁时，显式命令 MUST 立即报告 locked，不得隐式等待或重试。installed、no_update 和成功只读检查 MUST 返回零退出码；failed、locked 和非法命令 MUST 返回非零退出码。

#### Scenario: 安装失败保留当前 runtime

- **WHEN** 显式更新的下载、摘要校验、runtime 安装或健康检查失败
- **THEN** 系统 MUST 保留原 current
- **AND** 系统 MUST 记录失败阶段和稳定原因
- **AND** 系统 MUST 返回非零退出码

#### Scenario: 更新锁已被占用

- **WHEN** 另一个更新任务已经持有同一安装目录的更新锁
- **THEN** 显式命令 MUST 立即报告 locked
- **AND** 系统 MUST NOT 修改 current
- **AND** 系统 MUST 返回非零退出码

#### Scenario: 成功结果的结构化输出

- **WHEN** 显式更新或检查正常完成
- **THEN** stdout MUST 保持 JSON 结果格式
- **AND** 结果 MUST 能区分 installed、available 和 no_update
- **AND** 结果 MUST 包含当前版本及适用时的可用或已安装版本

### Requirement: 下次启动生效与更新边界

显式更新 MUST 使用现有独立版本目录、完整性门禁、健康检查和 current/previous 指针。当前正在执行的命令 MUST 继续使用其启动时解析的 runtime；成功更新后后续命令 MUST 使用新 current。显式 runtime 更新 MUST NOT 修改 skill、用户配置、浏览器 profile、报告、下载产物或业务认证状态。

#### Scenario: 当前命令不被重启

- **WHEN** 显式 update 在一个 runtime 进程中成功安装更高版本
- **THEN** 当前 update 进程 MUST 不自重启或热替换模块
- **AND** 新版本 MUST 通过独立版本目录和生效指针保存

#### Scenario: 下一次命令使用新版本

- **WHEN** 新 runtime 通过已有完整性和健康检查并切换 current
- **THEN** 下一次从安装入口启动的命令 MUST 解析到新版本
- **AND** previous MUST 保留为显式回滚候选

#### Scenario: runtime 与 skill 边界保持独立

- **WHEN** 显式 update 安装新 runtime
- **THEN** 系统 MUST NOT 安装、删除或覆盖任何 agent skill 目录
- **AND** skill 兼容性 MUST 继续由现有 skill 安装和预检流程处理
