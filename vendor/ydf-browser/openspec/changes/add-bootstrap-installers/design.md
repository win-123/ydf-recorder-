## Context

现有发布清单已经提供 stable 版本、最低 Python、最低 skill、平台发布包 URL 和 SHA-256；发布 ZIP 已包含 POSIX/Windows runtime 安装器、launcher、wheel 和 skill 安装器。现有 `UpdateManager` 依赖已安装的 Python 包且只处理高于当前版本的更新，因此不能直接承担首次 bootstrap，但其受信源、平台选择、完整性和解压边界是新入口必须保持的一致契约。

公司内部域名只承载最终给用户复制的引导安装器。引导安装器仍访问现有 `061981.xyz` runtime 更新源；完整迁移更新源不属于本 change。

## Goals / Non-Goals

**Goals:**

- 用两个小型入口覆盖 macOS/Linux shell 与 Windows PowerShell。
- 在首次安装前执行与现有更新器一致的清单、URL、SHA-256 和 ZIP 路径校验。
- 把 runtime 安装、配置保护、launcher 和依赖安装继续交给发布包内现有安装器。
- 让同一入口可用于首次安装、旧版升级和当前 stable 版本修复。

**Non-Goals:**

- 不安装或管理 Python、系统包管理器和企业 CA。
- 不把 runtime 与 gov-ydfdev-browser skill 合并为同一生命周期。
- 不修改用户 shell profile，不收集凭据，不增加遥测。
- 不迁移现有 runtime 更新源，也不新增签名密钥体系。

## Decisions

### 两个平台入口复用同一发布契约，不新增安装管理器

POSIX 入口使用已要求的 Python 标准库完成 JSON、HTTPS、SHA-256 和 ZIP 安全处理；Windows 入口使用 PowerShell 5.1 与 .NET 内置能力完成相同行为。两者最终分别调用 `scripts/install-runtime.sh` 和 `scripts/install-runtime.ps1`。

拒绝在首次安装前调用 `UpdateManager`，因为模块尚未安装且同版本不会触发更新；也拒绝复制 venv、pip、Chromium、配置和 launcher 逻辑，因为现有 runtime 安装器已经是这些行为的单一入口。

### 固定现有 runtime 更新源

引导安装器内置 `https://061981.xyz/ydf-browser/release-manifest.json` 和唯一受信主机 `061981.xyz`。脚本可以托管在内部域名，但脚本来源不改变清单和发布包信任边界。

拒绝把任意 manifest URL 暴露为普通环境变量，因为这会把固定受信源退化为任意代码下载入口。若未来完整迁移内部更新源，应单独修改发布器、runtime 更新器和桥接版本。

### 下载到私有临时目录，退出时统一清理

两个入口都只在系统临时目录创建唯一子目录，先下载并校验 ZIP，再安全解压和定位单一包装根目录。无论成功或失败都清理下载与解压产物；用户安装目录只由包内 runtime 安装器写入。

### 成功输出保留 runtime-only 边界

包内 runtime 安装器继续输出版本、配置和 launcher 位置；bootstrap 只追加从已安装 release 执行 skill 安装器的命令。它不自动运行 skill 安装器，也不读取业务配置。

### Windows 注册用户级 PATH，POSIX 不修改 shell profile

Windows runtime 安装器在命令 wrapper 写入成功后，将实际 `$BinDir` 去重加入当前用户 `PATH`；它从 `HKCU\Environment` 读取未展开原值并保留已有注册表值类型，不请求管理员权限。比较时展开环境变量、解析绝对路径、忽略大小写和尾部分隔符，已有语义重复项只保留第一个且其他条目的原始文本与顺序不变。PowerShell bootstrap 使用同一比较规则同步当前进程 `PATH`，因此 `irm | iex` 返回后同一窗口即可运行命令。

POSIX 安装继续只创建 `~/.local/bin/ydf-browser` 链接，不修改 shell profile。直接用 `powershell -File` 启动的子进程不能改变父进程环境，新 PATH 至少在后续登录会话生效。

## Risks / Trade-offs

- [PowerShell 5.1 与现代 PowerShell 的 HTTP/ZIP 对象存在差异] → 只使用 Windows 11 内置且可真实验证的 API，并在 Win11 ARM64 上执行完整预览安装。
- [发布站或 CDN 返回跨主机重定向] → 检查最终 URL 主机；不受信重定向直接失败。
- [Python 缺失使“一键”安装不能完成] → 下载发布包前明确失败并给出 Python 3.11+ 前置要求，不扩大到操作系统包管理。
- [同版本重装会重新创建 venv 并下载 Chromium] → 将其保留为确定性的修复语义，避免新增易漂移的本地版本探测与跳过分支。
- [真实 Windows 验证环境是 ARM64] → 验证 PowerShell、网络、SHA、ZIP、Python、venv、Chromium 和 launcher 的 Windows 路径，但不把它描述为 Windows x86_64 专项证明。
- [用户 PATH 已包含同一目录或重复执行安装] → 使用 PowerShell 默认不区分大小写的条目比较去重，只在缺失时追加。

## Migration Plan

1. 先用本地假发布源完成失败可见的聚焦红绿测试。
2. 在 macOS 使用隔离 `YDF_BROWSER_HOME` 和 `YDF_BROWSER_BIN_DIR` 完成发布包安装验证。
3. 将两个入口临时上传为 `install-preview.sh` 和 `install-preview.ps1`。
4. 在干净 Win11 当前用户下先证明缺少 Python 的失败路径，再安装官方 Python 3.12 并验证完整安装与重复执行。
5. 删除预览文件；最终公司内部域名发布和安装命令由用户手工完成。

回滚只需撤下 bootstrap 文件；已经安装的 runtime 继续使用现有版本切换、后台更新和显式 rollback 机制。
