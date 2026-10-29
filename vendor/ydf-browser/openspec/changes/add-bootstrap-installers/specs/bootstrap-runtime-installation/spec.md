## Purpose

定义用户通过稳定的 shell 或 PowerShell 入口，从受信发布源查询、校验并安装最新 stable `ydf-browser` runtime 的跨平台引导安装行为。

## ADDED Requirements

### Requirement: 跨平台引导安装入口
系统 MUST 提供可通过标准输入执行的 POSIX shell 与 PowerShell 引导安装器；POSIX 入口覆盖 macOS，PowerShell 入口覆盖 Windows，脚本托管位置与 runtime 更新源相互独立。

#### Scenario: macOS 用户运行 shell 入口
- **WHEN** macOS 用户通过 `curl` 获取 POSIX 引导安装器并交给 `sh` 执行
- **THEN** 系统查询 stable 发布清单并进入当前平台 runtime 安装流程

#### Scenario: Windows 用户运行 PowerShell 入口
- **WHEN** Windows 用户通过 `Invoke-RestMethod` 获取 PowerShell 引导安装器并执行
- **THEN** 系统查询 stable 发布清单并进入当前平台 runtime 安装流程

#### Scenario: 引导安装器托管在另一个受信站点
- **WHEN** 引导安装器由公司内部 HTTPS 域名提供
- **THEN** 脚本仍从内置 runtime 更新源查询发布清单和发布包

### Requirement: 明确 Python 前置条件
引导安装器 MUST 在下载发布包前找到满足发布清单要求的 Python 3.11 或更高版本；它 MUST NOT 自动安装 Python。

#### Scenario: 缺少兼容 Python
- **WHEN** 当前用户环境中找不到 Python 3.11 或更高版本
- **THEN** 引导安装器以非零状态退出并明确说明 Python 最低版本要求
- **AND** 系统不创建或切换 `ydf-browser` runtime

### Requirement: 校验 stable 清单与平台发布包
引导安装器 MUST 接受 schema version 1、stable channel、合法版本与兼容性字段，并按 `os-arch`、`os`、`all` 的顺序选择当前平台发布包。发布清单、发布包及其最终重定向 MUST 使用内置受信主机的 HTTPS 地址。

#### Scenario: 存在平台架构专用发布包
- **WHEN** 发布清单同时包含当前 `os-arch`、当前 `os` 和 `all` 发布包
- **THEN** 引导安装器选择当前 `os-arch` 发布包

#### Scenario: 仅有全平台发布包兼容
- **WHEN** 发布清单只包含 `all` 发布包
- **THEN** 引导安装器选择 `all` 发布包

#### Scenario: 清单或发布包地址不受信
- **WHEN** 发布清单地址、发布包地址或最终重定向不是内置受信主机的 HTTPS 地址
- **THEN** 引导安装器拒绝继续并且不调用 runtime 安装器

#### Scenario: 清单要求更高 Python 版本
- **WHEN** 发布清单的 `min_python` 高于当前找到的 Python 版本
- **THEN** 引导安装器以非零状态退出并说明实际版本与最低版本

### Requirement: 强制发布包完整性与安全解压
引导安装器 MUST 在解压前校验发布包 SHA-256，并拒绝包含目标目录之外路径、缺失 `VERSION`、缺失项目 wheel 或缺失当前平台 runtime 安装器的发布包。

#### Scenario: 发布包摘要匹配
- **WHEN** 下载字节的 SHA-256 与发布清单一致且发布包结构完整
- **THEN** 引导安装器安全解压发布包并定位其实际根目录

#### Scenario: 发布包摘要不匹配
- **WHEN** 下载字节的 SHA-256 与发布清单不一致
- **THEN** 引导安装器删除临时文件、以非零状态退出并且不调用 runtime 安装器

#### Scenario: 发布包包含越界路径
- **WHEN** ZIP 成员会被解压到临时目标目录之外
- **THEN** 引导安装器拒绝该发布包并且不写入越界路径

### Requirement: 现有 runtime 安装器保持权威入口
引导安装器 MUST 委托发布包内当前平台的 runtime 安装器完成版本目录、venv、依赖、Chromium、配置和命令入口安装；它 MUST NOT 复制这些安装职责。

#### Scenario: 首次 runtime 安装成功
- **WHEN** 发布包验证通过且包内 runtime 安装器成功退出
- **THEN** 引导安装器以零状态退出并输出已安装版本、配置位置、命令入口和可选 skill 安装命令

#### Scenario: runtime 安装器失败
- **WHEN** 包内 runtime 安装器以非零状态退出
- **THEN** 引导安装器返回非零状态且不报告安装成功

#### Scenario: 重复执行引导安装器
- **WHEN** 用户在已有安装上再次执行引导安装器
- **THEN** 系统重新委托 stable 发布包内的 runtime 安装器完成升级或修复
- **AND** 已有 `env.yaml`、`env.local.yaml`、profile 和报告保持不被覆盖

### Requirement: 引导安装器保持非交互和用户级边界
引导安装器 MUST 不请求业务凭据、不修改 shell profile、不请求管理员权限，并且 MUST 不默认安装 agent skill。

#### Scenario: runtime-only 安装完成
- **WHEN** 引导安装器完成 runtime 安装
- **THEN** 系统没有修改 shell profile 或 agent skill 目录
- **AND** 输出从已安装 release 后续安装 skill 的显式命令

#### Scenario: Windows 自动注册用户级命令目录
- **WHEN** Windows runtime 安装器成功写入 `ydf-browser.cmd`
- **THEN** 系统将实际命令目录去重后加入当前用户 `PATH`，不请求管理员权限
- **AND** PowerShell 引导安装器通过 `irm | iex` 在当前会话运行时，同一会话可立即执行 `ydf-browser`

#### Scenario: Windows 重复安装不重复注册 PATH
- **WHEN** Windows 用户再次运行 runtime 或引导安装器
- **THEN** 当前用户 `PATH` 中实际命令目录只保留一个条目
