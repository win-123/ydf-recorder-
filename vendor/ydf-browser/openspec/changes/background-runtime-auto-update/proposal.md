## Why

当前安装版 `ydf-browser` 已经按版本保存 runtime 并通过 `current` 指向生效版本，但用户仍需要手工获取发布包和重新安装，容易长期停留在旧版本。现有版本目录结构已经具备后台准备新版本、在下一次命令启动时切换且不打断当前运行的基础，因此现在适合补齐无感更新闭环。

## What Changes

- 新增稳定发布清单，按平台提供 runtime 发布包地址、SHA-256、最低 Python 版本和最低兼容 skill 版本。
- 在命令启动时按 24 小时冷却周期后台检查更新；检查、下载和安装不阻塞或改变当前命令。
- 将新版本安装到独立版本目录，完成完整性和 runtime 健康检查后原子切换 `current`，后续命令自动使用新版本。
- 同一安装目录只允许一个后台更新任务；失败静默记录本地状态，由 `doctor` 展示。
- 保留当前版本和上一版本，提供显式回滚边界；不因 DSL 或业务运行失败自动回滚。
- 保留用户配置、`env.local.yaml`、持久化浏览器 profile 和报告，不请求提权，不复用浏览器登录态，不增加遥测。
- 默认开启后台更新，支持 `YDF_BROWSER_AUTO_UPDATE=0` 关闭；更新源固定为受信 HTTPS 主机，覆盖 macOS、Windows 和 Linux。

## Capabilities

### New Capabilities

- `background-runtime-auto-update`: 定义 runtime 发布清单、后台检查、无中断安装、版本切换、失败状态、回滚和用户数据边界。

### Modified Capabilities

- 无。现有发布 wheel 刷新和浏览器 profile 生命周期要求保持不变。

## Impact

- 影响安装版启动入口、runtime 安装目录和版本指针管理。
- 影响发布包生成、平台发布清单、CLI `doctor` 状态输出和用户更新开关。
- 增加跨平台更新检查、下载、SHA-256 校验、安装锁和失败状态持久化能力；继续使用现有发布 ZIP、wheel 和 Playwright runtime。
- 需要为 macOS、Windows、Linux 的发布源准备按平台可解析的稳定发布清单，并增加隔离安装目录和本地测试源验收。
