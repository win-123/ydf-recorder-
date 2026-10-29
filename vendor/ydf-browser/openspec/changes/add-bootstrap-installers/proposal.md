## Why

当前用户必须先手工下载并解压发布包，再选择平台安装器；这增加了首次安装的步骤，也让用户容易绕过发布清单与 SHA-256 校验。需要提供面向 macOS/Linux 与 Windows 的稳定引导安装器，从现有发布源完成受控的一键 runtime 安装。

## What Changes

- 新增 POSIX shell 与 PowerShell 引导安装器，分别支持 `curl | sh` 和 `irm | iex`。
- 引导安装器读取 stable 发布清单，选择当前平台发布包，校验受信 HTTPS 地址、SHA-256 和解压边界后，委托发布包内已有 runtime 安装器。
- 首次安装保持非交互、用户级和 runtime-only，不安装 Python、不修改 shell profile、不覆盖已有配置；Windows 自动注册用户级命令目录，安装结束后提示可选的 skill 安装入口。
- 重复执行同一入口时重新安装当前 stable 版本，用于旧版升级或当前版本修复。
- 增加聚焦自动化测试、安装文档以及 macOS 和真实 Windows 验证门禁。

## Capabilities

### New Capabilities

- `bootstrap-runtime-installation`: 定义跨平台引导安装器的发布清单查询、下载校验、委托安装、重复执行和用户可见结果。

### Modified Capabilities

无。

## Impact

- 新增 `scripts/install.sh`、`scripts/install.ps1` 及其聚焦测试。
- 更新 Windows runtime 安装过程、发布包文件清单、`README.md`、`docs/release/tester-guide.md` 和领域词汇。
- 继续使用现有发布清单、发布 ZIP、runtime 安装器、配置目录和自动更新机制，不增加运行时依赖。
- 临时预览脚本将上传到现有发布站完成真实安装验证；最终公司内部域名部署由用户手工完成。
