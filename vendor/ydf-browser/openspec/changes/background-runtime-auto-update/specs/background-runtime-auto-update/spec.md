## Purpose

为安装版 `ydf-browser` 提供跨平台、可回滚且不打断当前命令的 runtime 后台更新能力，使后续命令能够自动使用已经校验的新版本，同时保护用户配置、浏览器 profile 和业务运行边界。

## ADDED Requirements

### Requirement: 受信稳定发布清单

系统 MUST 从固定受信 HTTPS 更新源读取稳定发布清单。发布清单 MUST 声明自身 schema 版本、稳定频道、runtime 版本、目标平台发布包、发布包 URL、SHA-256、最低 Python 版本和最低兼容 skill 版本；客户端 MUST 拒绝缺少必要字段、版本不高于当前版本、平台不匹配、非 HTTPS 或非受信主机的清单和发布包。

#### Scenario: 选择当前平台的稳定新版本

- **WHEN** 更新源返回结构完整且版本高于当前版本的稳定清单
- **THEN** 系统 MUST 选择当前操作系统和机器架构对应的发布包
- **AND** 系统 MUST 将发布包 URL、SHA-256、最低 Python 版本和最低兼容 skill 版本纳入本次更新状态

#### Scenario: 清单或发布源不受信

- **WHEN** 清单缺少必要字段、发布包 URL 使用非 HTTPS、主机不在受信范围或 HTTPS 重定向离开受信范围
- **THEN** 系统 MUST 拒绝本次更新
- **AND** 系统 MUST 保留当前生效版本
- **AND** 系统 MUST 记录可诊断的失败原因

#### Scenario: 没有更高的稳定版本

- **WHEN** 清单中的稳定版本不高于当前版本
- **THEN** 系统 MUST 将本次检查记录为无可用更新
- **AND** 系统 MUST NOT 下载或修改本地 runtime

### Requirement: 后台更新检查

已安装命令入口 MUST 在后台更新开启且距离上次检查至少 24 小时时，启动一个脱离当前终端的 best-effort 更新任务。后台检查 MUST NOT 阻塞当前命令、改变当前命令已使用的 runtime 或要求用户交互；`YDF_BROWSER_AUTO_UPDATE=0` MUST 禁止自动检查和安装。

#### Scenario: 启动命令时后台检查

- **WHEN** 用户通过已安装命令入口启动任意 `ydf-browser` 命令，后台更新未关闭且检查冷却周期已到
- **THEN** 系统 MUST 尽快启动后台更新任务并立即继续原命令
- **AND** 原命令 MUST 使用启动时解析到的 runtime 版本

#### Scenario: 检查处于冷却周期

- **WHEN** 距离上次完成或失败的更新检查不足 24 小时
- **THEN** 系统 MUST 跳过本次后台检查
- **AND** 系统 MUST NOT 因跳过检查而改变原命令的退出语义

#### Scenario: 用户关闭后台更新

- **WHEN** 用户设置 `YDF_BROWSER_AUTO_UPDATE=0`
- **THEN** 系统 MUST NOT 启动后台更新任务
- **AND** `ydf-browser update --check` MUST 仍可被用户显式执行

### Requirement: 不打断运行的分阶段安装

系统 MUST 将新 runtime 安装到独立的版本目录，不得覆盖当前生效版本目录。只有在发布包完整性、运行环境和兼容性检查全部通过后，系统才 MUST 原子更新生效指针；已经开始的命令 MUST 继续使用其启动时的 runtime，后续命令 MUST 使用新版本。

#### Scenario: 当前运行期间完成后台安装

- **WHEN** 一个 DSL 运行正在使用旧版本且后台任务完成新版本安装
- **THEN** 旧版本运行 MUST 继续执行，不得被终止或重启
- **AND** 新版本 MUST 保持在独立版本目录

#### Scenario: 校验通过后切换后续命令

- **WHEN** 新版本安装和健康检查成功
- **THEN** 系统 MUST 原子切换 `current` 到新版本
- **AND** 下一次从安装入口启动的命令 MUST 指向新版本
- **AND** 用户配置、`env.local.yaml`、浏览器 profile 和已有报告 MUST 保持不变

### Requirement: 完整性与健康门禁

系统 MUST 在安装前验证发布包 SHA-256，并 MUST 在切换前验证新 runtime 能够通过不依赖业务配置的健康检查。任一校验失败时，系统 MUST 不切换生效指针、不删除当前版本，并 MUST 记录失败原因。

#### Scenario: 发布包摘要不匹配

- **WHEN** 下载内容的 SHA-256 与清单声明不一致
- **THEN** 系统 MUST 删除或隔离未验证的临时下载内容
- **AND** 系统 MUST 保留当前生效版本
- **AND** 系统 MUST 将更新记录为完整性校验失败

#### Scenario: 新 runtime 健康检查失败

- **WHEN** 新版本安装完成但 `doctor --skip-config` 或等价的 runtime 健康检查失败
- **THEN** 系统 MUST 不切换 `current`
- **AND** 系统 MUST 保留旧版本继续服务后续命令
- **AND** 系统 MUST 记录新版本和健康检查失败原因

### Requirement: 单更新任务与本地更新状态

同一个安装目录 MUST 同时最多运行一个更新任务。系统 MUST 在用户安装目录保存最近检查、可用版本、安装结果、失败原因和时间信息；`doctor` MUST 展示该状态，但后台更新失败 MUST NOT 改变当前 runtime 健康检查的既有退出语义。

#### Scenario: 并发启动多个更新任务

- **WHEN** 多个 `ydf-browser` 命令同时触发后台更新
- **THEN** 只有一个更新任务 MUST 获得更新锁并执行
- **AND** 其它任务 MUST 跳过更新并继续执行原命令

#### Scenario: doctor 展示后台更新失败

- **WHEN** 最近一次后台检查或安装失败
- **THEN** `ydf-browser doctor` MUST 展示最近更新状态、目标版本和稳定失败原因
- **AND** `doctor` MUST 仍按 Python、Playwright、配置和转发目标的既有检查结果决定退出码

### Requirement: 显式更新控制与回滚

系统 MUST 提供 `ydf-browser update --check` 供用户前台检查更新，并 MUST 提供显式回滚到上一保留版本的能力。系统 MUST NOT 因 DSL 断言不符合、业务数据失败或真实页面验证失败自动回滚 runtime。

#### Scenario: 用户显式检查更新

- **WHEN** 用户运行 `ydf-browser update --check`
- **THEN** 系统 MUST 前台返回当前版本、可用版本或无更新结果
- **AND** 该命令 MUST NOT 在未明确执行安装操作时改变 `current`

#### Scenario: 用户显式回滚

- **WHEN** 用户请求回滚且存在上一保留版本
- **THEN** 系统 MUST 将后续命令的生效指针切换到上一版本
- **AND** 已经开始的命令 MUST 继续使用其启动时的版本
- **AND** 系统 MUST 保留可诊断的回滚结果

#### Scenario: 没有可回滚版本

- **WHEN** 用户请求回滚但没有上一保留版本
- **THEN** 系统 MUST 返回明确失败结果
- **AND** 系统 MUST NOT 修改当前生效指针

### Requirement: 版本保留与 skill 边界

系统 MUST 至少保留当前版本和上一版本，并只允许在一次成功切换之后清理更旧的版本目录。后台 runtime 更新 MUST NOT 覆盖任意 skill 安装目录；当清单声明的最低 skill 版本高于可检测到的 skill 版本时，`doctor` 或 AI 兼容性预检 MUST 提示或阻断相应能力。

#### Scenario: 成功更新后保留上一版本

- **WHEN** 新版本成功切换为 `current`
- **THEN** 系统 MUST 保留切换前的版本作为上一版本
- **AND** 系统 MUST NOT 删除当前运行可能仍在使用的旧版本目录

#### Scenario: runtime 更新不覆盖 skill

- **WHEN** 后台任务安装新 runtime
- **THEN** 系统 MUST NOT 修改 Codex、Claude Code 或通用 agent 的 skill 目录
- **AND** 新 runtime MUST 继续报告清单要求的最低 skill 版本

#### Scenario: skill 版本不兼容

- **WHEN** 已安装 skill 低于新 runtime 清单声明的最低兼容版本
- **THEN** `doctor` 或 AI 兼容性预检 MUST 报告不兼容状态
- **AND** AI 开发验证 MUST NOT 将不兼容状态当作可验证运行

### Requirement: 用户数据、权限与隐私边界

后台更新 MUST 只写入用户安装目录和临时下载目录，不得请求 sudo、UAC 或其它管理员权限。更新请求 MUST 不复用浏览器 Cookie、业务 session 或认证上下文；系统 MUST NOT 为后台更新新增遥测或上传本地运行信息。

#### Scenario: 用户目录内完成更新

- **WHEN** 用户安装目录可写且后台更新可用
- **THEN** 系统 MUST 在用户目录内完成下载、安装和版本切换
- **AND** 系统 MUST NOT 改写用户配置、profile 或报告目录

#### Scenario: 发布源不可访问

- **WHEN** 网络、代理或证书导致发布源不可访问
- **THEN** 原命令 MUST 继续按既有流程运行
- **AND** 系统 MUST 只在本地更新状态中记录失败原因
- **AND** 系统 MUST NOT 读取或转发浏览器认证信息补救请求
