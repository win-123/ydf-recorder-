## 1. 发布清单与发布包

- [x] 1.1 定义稳定发布清单的 JSON schema、版本字段、平台/架构包映射、SHA-256、`min_python` 和 `min_skill_version`，并补充发布源受信校验。
- [x] 1.2 扩展 `scripts/package_release.py`，在生成 macOS、Windows、Linux 发布包时生成或校验对应发布元数据，并保持现有 wheel 刷新行为。
- [x] 1.3 增加发布包审计，确认 ZIP 不包含配置、报告、认证信息或旧 wheel，并确认清单引用的包和摘要一致。

## 2. Runtime 更新核心

- [x] 2.1 新增 runtime 更新模块，完成固定 HTTPS 清单读取、稳定版本比较、平台选择、24 小时冷却和 `YDF_BROWSER_AUTO_UPDATE=0` 判断。
- [x] 2.2 实现下载临时文件、SHA-256 校验、受信重定向检查、安装锁、本地更新状态和稳定失败原因码。
- [x] 2.3 复用现有 runtime 安装语义，把新版本安装到 staging 目录，安装 wheel 和 Playwright 依赖，并执行 `doctor --skip-config` 健康检查。
- [x] 2.4 实现跨平台 `current`/`previous` 指针切换、旧版本保留和更旧版本清理；任何中间失败都不得改变当前生效版本。
- [x] 2.5 确认更新过程不修改用户配置、`env.local.yaml`、浏览器 profile、报告，不请求提权，也不读取或转发业务认证信息。

## 3. 安装入口与 CLI

- [x] 3.1 修改 `bin/ydf-browser` 和 `bin/ydf-browser.cmd`，在不阻塞原命令的前提下启动脱离终端的后台更新任务，并保留旧 runtime 的进程生命周期。
- [x] 3.2 增加 `ydf-browser update --check` 和显式回滚命令，明确输出当前版本、可用版本、失败原因和回滚结果。
- [x] 3.3 扩展 `ydf-browser doctor`，以非阻断方式展示最近更新状态、目标版本、skill 兼容性和稳定失败原因，保持既有退出码语义。
- [x] 3.4 为命令帮助和错误路径补充自动更新开关、检查、回滚和权限边界说明。

## 4. Runtime 与 skill 兼容边界

- [x] 4.1 为 `install-skill.sh` 和 `install-skill.ps1` 写入可检测的 skill 版本元数据，且不改变现有 `codex`、`claude`、`agents` 和 `all` 目标语义。
- [x] 4.2 让 `doctor` 与 AI 兼容性预检读取已安装 skill 元数据，在低于 `min_skill_version` 时报告或阻断相应 AI 开发验证，并确保 runtime 更新不覆盖 skill 目录。

## 5. 测试与隔离验收

- [x] 5.1 为清单解析、版本比较、冷却、SHA-256、受信主机、锁、状态、禁用开关和失败保留旧版本补充聚焦单元测试。
- [x] 5.2 为 staging 安装、健康检查、current/previous 切换、显式检查、回滚、doctor 状态和 skill 兼容性补充 CLI/集成测试。
- [x] 5.3 使用隔离 `YDF_BROWSER_HOME` 和可替换测试源验证后台任务不阻塞当前命令、旧进程继续运行、并发触发只执行一次，以及 macOS/Linux/Windows 入口的关键分支。
- [x] 5.4 使用真实 `scripts/package_release.py --platform all` 产物完成发布 ZIP、wheel、清单和安装入口审计。

## 6. 用户文档与发布说明

- [x] 6.1 更新 `README.md`、`docs/release/tester-guide.md` 和 `docs/release/ai-dev-guide.md`，说明后台检查、关闭开关、状态查看、显式检查、回滚和 skill 独立更新边界。
- [x] 6.2 更新 `docs/release/changelog.md`，记录用户可见的 runtime 自动更新能力和安全/隐私边界。
- [x] 6.3 增加发布源清单格式和本地隔离验收说明，避免把内部发布地址、认证信息或运行证据写入仓库。

## 7. 交付验证

- [x] 7.1 运行 `openspec validate background-runtime-auto-update --strict` 和 `./scripts/check_openspec_language.py --change background-runtime-auto-update`。
- [x] 7.2 运行相关聚焦测试、完整 `./.venv/bin/python -m pytest -q` 和 `git diff --check`。
- [x] 7.3 使用当前源码 CLI 验证 `doctor`、`update --check`、回滚和安装版下一次命令指向新版本的行为。
- [x] 7.4 在隔离安装根执行一次成功更新、一次摘要或健康检查失败保留旧版本、一次并发触发和一次显式回滚，并保存仅供本轮使用的临时证据。
