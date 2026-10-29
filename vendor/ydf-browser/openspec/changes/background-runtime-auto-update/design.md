## Context

参见 [proposal.md](./proposal.md) 的 `Why`。当前正式安装流程把发布包安装到 `YDF_BROWSER_HOME/releases/<version>`，并通过 `current` 入口和独立 `.venv` 执行 runtime；配置位于安装目录之外，浏览器 profile 也由 `YDF_BROWSER_HOME` 管理。当前缺少发布清单、后台检查、安装锁、健康门禁和状态展示。

安装包已经包含 macOS/Linux shell 入口、Windows PowerShell 安装器和对应命令入口。runtime 自身使用标准库、Playwright 和现有 wheel，不应为了更新能力引入常驻服务、额外依赖或新的认证链路。

## Goals / Non-Goals

**Goals:**

- 在现有版本目录和 `current` 入口上增加后台、无中断的 runtime 更新。
- 用固定 HTTPS 清单、SHA-256、平台选择和最低兼容版本保护发布边界。
- 让 macOS、Windows、Linux 共用同一套更新语义，同时保留各平台入口的最小差异。
- 让失败可诊断、可显式回滚，但不把业务运行失败误判为 runtime 需要回滚。
- 保持配置、profile、报告、登录链路和现有 CLI 二值退出语义不变。

**Non-Goals:**

- 不自动更新 `gov-ydfdev-browser` skill，不覆盖 Codex、Claude Code 或通用 agent 的 skill 目录。
- 不建设操作系统常驻服务、完整遥测系统、多发布频道、强制升级或任意更新源配置。
- 不复用浏览器 Cookie、业务 session、环境登录态或任何认证上下文访问发布源。
- 不在运行中的 Python 进程内热替换模块，也不为业务运行失败增加自动 runtime 回滚。

## Decisions

### 1. 以发布清单作为唯一更新输入

新增稳定 JSON 发布清单，至少包含 `schema_version`、`channel`、`version`、`platforms`、`url`、`sha256`、`min_python` 和 `min_skill_version`。清单按平台和机器架构提供发布 ZIP；客户端只接受固定受信 HTTPS 主机和仍在该主机上的 HTTPS 重定向。

清单由发布流程生成并随发布 ZIP 外部发布。更新器只解析清单和下载包，不读取 Git、运行源码构建或从业务系统接口推导版本。选择 JSON 和标准库解析而不是引入包管理服务，是因为 v1 只有一个稳定频道和固定发布包格式。

### 2. 用安装入口触发 best-effort 后台任务

已安装的 `bin/ydf-browser` 和 `bin/ydf-browser.cmd` 在解析当前 release 后，先检查 `YDF_BROWSER_AUTO_UPDATE` 和本地冷却状态；满足条件时启动一个脱离终端的更新子进程，然后立即执行当前 release 的原命令。`YDF_BROWSER_AUTO_UPDATE=0` 在入口层生效，避免已经启动 Python CLI 后才发现需要跳过更新。

冷却状态保存在 `YDF_BROWSER_HOME` 下，每 24 小时最多启动一次检查。更新子进程不等待业务命令、不继承需要写入报告的 stdout/stderr，也不改变父命令退出码；网络错误只进入本地状态文件。

选择入口触发而不是安装操作系统定时任务，是为了复用现有安装包、避免三套平台服务注册和卸载逻辑，并保持“用户使用工具时才更新”的可预期边界。

### 3. 更新器使用独立安装目录和共享安装管理器

新增轻量更新模块负责清单读取、版本比较、下载临时文件、SHA-256 校验、更新锁、状态写入和调用安装管理器。现有 shell/PowerShell 安装器与后台更新应共享版本目录、wheel 安装、Playwright 安装、配置初始化和版本指针切换的核心语义；平台脚本只保留 Python 不可用时的引导职责。

后台任务按以下顺序执行：

1. 获取安装锁，读取并校验稳定清单。
2. 在安装目录外的临时位置下载发布 ZIP，校验 SHA-256，并确认版本、平台和最低 Python 要求。
3. 解压到 `releases/<version>.staging`，创建独立 runtime，安装内置 wheel 和 Playwright 浏览器依赖。
4. 对 staging runtime 执行 `doctor --skip-config` 等价健康检查，并检查 skill 兼容元数据。
5. 将 staging 目录改名为正式版本目录，原子更新 `current`，把切换前版本保留为上一版本。
6. 写入成功状态，清理更旧且不属于 current/previous 的版本目录和临时文件。

任何中间步骤失败都只清理未验证 staging/临时内容，不改变 `current`。

### 4. 通过平台适配完成生效指针切换

Unix 使用临时链接加原子替换实现 `current` 切换；Windows 使用安装目录内的 `current.txt`/`previous.txt` 文本指针和临时文件替换，不要求目录符号链接或管理员权限。平台适配必须提供同一抽象：读取 current、切换 current、保留 previous、读取当前版本。切换前不得删除旧指针，切换失败必须能继续解析旧 current。

不采用覆盖当前目录或先删除 current 再创建新链接，因为当前命令可能仍在旧目录运行，且中断会留下不可启动安装。也不在切换时删除上一版本，避免仍存活的旧进程引用失效路径。

### 5. 通过文件锁和本地状态保持可诊断

更新锁放在 `YDF_BROWSER_HOME`，采用各平台可用的进程级文件锁；抢不到锁的后台任务直接跳过。状态文件只保存当前版本、最后检查时间、可用版本、安装阶段、结果和稳定原因码，不保存认证信息、业务数据或完整网络正文。

`doctor` 增加非阻断的 update 状态展示。其总体退出码继续由现有 CLI、Python、Playwright、配置和转发目标检查决定，不能因为一次后台更新网络失败而把现有可用 runtime 判为不可用。`ydf-browser update --check` 复用同一清单解析与状态输出但以前台方式执行；回滚命令只切换上一保留版本，不启动浏览器或读取业务配置。

### 6. 将 skill 兼容性作为声明而非更新耦合

runtime 发布清单声明最低 skill 版本；安装 skill 时写入可检测的版本元数据，`doctor` 和 AI 兼容性预检读取各支持 skill 根目录的元数据并报告最低版本不满足。后台 runtime 更新永远不复制或删除 skill 目录。

这样保留 runtime 与 skill 的独立发布边界，又避免新 runtime 静默运行在不兼容的 AI 验证 skill 上。普通 DSL 运行的既有行为不因为 skill 未安装而失败；只有需要 skill 兼容能力的预检按既有 `contract_incompatible` 语义阻断。

### 7. 测试使用隔离安装根和可替换测试源

测试不依赖生产发布服务。更新模块接受测试内部的 manifest/download transport 或本地测试源注入，但生产入口仍只允许固定受信 HTTPS 源。每个测试使用独立 `YDF_BROWSER_HOME`，构造最小版本目录和可执行 fake runtime，覆盖成功、摘要错误、健康检查错误、并发锁、冷却跳过、禁用开关、状态展示、回滚和旧进程继续运行。

发布验证继续使用 `scripts/package_release.py --platform all` 生成真实 ZIP，并检查 ZIP 中只含预期 runtime、wheel、安装入口和发布清单，不把报告、配置或认证信息带入包内。

## Risks / Trade-offs

- [后台任务由每次命令入口触发，工具长期不使用时不会更新] → 这是避免常驻服务的有意边界；用户下一次使用时立即触发检查。
- [Windows 目录链接替换的原子能力弱于 Unix] → 将指针切换隔离在平台适配层，先完成 staging 和健康检查；任何替换失败都保留旧 current。
- [发布源不可访问会长期停留旧版本] → `doctor` 展示最近状态和失败原因，下一次冷却周期自动重试，用户也可显式 `update --check`。
- [新 runtime 与旧 skill 不兼容] → 清单声明最低 skill 版本，预检阻断不兼容 AI 验证，但更新器不覆盖 skill 目录。
- [更新器本身位于旧 release 中] → 旧 release 只负责安装新版本和切换指针；当前进程不被替换，保留 current/previous 使旧进程引用始终有效。
- [后台更新可能产生额外网络和磁盘开销] → 24 小时冷却、单任务锁、仅下载更高版本和成功后清理更旧版本限制资源使用。

## Migration Plan

1. 为当前发布流程增加稳定清单生成和按平台包元数据，确保已有发布 ZIP 仍可手工安装。
2. 先实现共享安装管理器和状态/锁能力，再让 shell、PowerShell 和 CLI 入口调用它；保留现有安装命令兼容行为。
3. 在隔离安装根中完成本地测试源的成功、失败、并发和回滚测试，再做真实 ZIP 审计。
4. 为 `doctor`、`update --check`、回滚、自动更新开关和 skill 兼容提示补充用户文档与命令帮助。
5. 如果新版本健康检查或指针切换失败，保持旧 current；如果上线后需要回退，由用户显式执行回滚，不删除旧版本直到回滚窗口结束。
