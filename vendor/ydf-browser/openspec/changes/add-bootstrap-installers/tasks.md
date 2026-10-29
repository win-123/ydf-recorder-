## 1. 聚焦回归测试

- [x] 1.1 先新增并运行 POSIX 引导安装器行为测试，证明缺失实现时在 stable 清单安装、SHA-256 拒绝和 ZIP 越界拒绝场景按预期失败
- [x] 1.2 新增发布包收集测试，覆盖两个 bootstrap 文件、POSIX 执行权限和 dry-run 文件清单

## 2. 引导安装器实现

- [x] 2.1 实现 `scripts/install.sh`，完成 Python 前置检查、受信清单与平台选择、HTTPS 下载、SHA-256、安全解压、委托安装和 skill 提示
- [x] 2.2 实现 `scripts/install.ps1`，使用 PowerShell 5.1/.NET 完成对应 Windows 行为
- [x] 2.3 将两个入口加入发布包白名单并保持现有 runtime、配置和 skill 生命周期不变

## 3. 领域语言和用户文档

- [x] 3.1 在 `CONTEXT.md` 增加“引导安装器”术语并明确它与 runtime 安装器、后台更新的边界
- [x] 3.2 更新 `README.md` 和 `docs/release/tester-guide.md`，给出内部域名的一键命令、Python 前置、PATH 提示和后续 skill 安装命令

## 4. 验证和临时发布

- [x] 4.1 运行聚焦 pytest、shell 语法检查、发布包 dry-run 和 OpenSpec 严格/语言检查
- [x] 4.2 上传 `install-preview.sh` 与 `install-preview.ps1`，在 macOS 隔离目录完成公网脚本安装、版本、DSL validate 和 doctor 验证
- [x] 4.3 在真实 Win11 当前用户下验证无 Python 失败，安装官方 Python 3.12 后完成公网 PowerShell 安装、版本、doctor 和重复安装验证
- [x] 4.4 删除预览文件，运行完整 pytest、`git diff --check`、发布包审计和最终 OpenSpec 门禁

## 5. Windows 用户级 PATH

- [x] 5.1 新增并运行 Windows PATH 红测试，覆盖命令目录缺失、当前会话不可执行和重复条目
- [x] 5.2 修改 Windows runtime 与引导安装器，持久化用户级 PATH、同步当前 PowerShell 会话并更新安装文档
- [x] 5.3 在真实 Win11 中验证首次注册、同一会话命令可用、重复安装不重复，并重跑聚焦、完整 pytest 与 OpenSpec 门禁
