# Runtime 后台更新

安装版 `ydf-browser` 默认在命令启动时发起后台更新检查。检查、下载和安装不等待当前命令；当前命令继续使用启动时解析到的旧 runtime，后续命令自动使用完成健康检查后的新版本。

## 用户控制

```bash
# 立即检查并安装更高 stable runtime；当前命令不重启，下一次命令使用新版本
ydf-browser update

# 查看更新状态并前台检查，不安装新版本
ydf-browser update --check

# 回滚到上一保留 runtime
ydf-browser update rollback

# 关闭命令入口触发的后台更新；显式 update 和 update --check 仍可用
YDF_BROWSER_AUTO_UPDATE=0 ydf-browser doctor
```

更新状态保存在 `YDF_BROWSER_HOME`（默认 `~/.ydf-browser`）下的 `update-state.json`，`ydf-browser doctor` 会展示最近检查、可用版本、结果和失败原因。更新失败不会改变当前 runtime 的诊断和运行退出语义。

显式 `update` 和 `update --check` 都会绕过后台 24 小时冷却；前者只安装高于当前版本的 stable runtime，后者只检查不安装。`YDF_BROWSER_AUTO_UPDATE=0` 只关闭后台自动任务，不会阻止用户明确执行的显式命令。`update --check rollback` 等冲突组合会失败，不会修改 runtime。

更新只写用户安装目录及其临时目录，不修改 `config/env.yaml`、`config/env.local.yaml`、浏览器 profile 或报告，不请求管理员权限，也不读取业务登录态。更新器永远不覆盖 agent skill；skill 仍需通过 `ydf-browser install-skill` 独立更新。

## 发布清单

默认清单地址是 `https://061981.xyz/ydf-browser/release-manifest.json`。发布清单格式见 [`update-manifest.example.json`](./update-manifest.example.json) 和 [`schemas/update-manifest.schema.json`](../../schemas/update-manifest.schema.json)。清单包含稳定频道、runtime 版本、最低 Python/skill 版本，以及按平台和架构选择的 ZIP 地址与 SHA-256。客户端只接受内置受信 HTTPS 源及其同源重定向。

发布 ZIP 必须由 `scripts/package_release.py --platform all` 生成；发布负责人将 ZIP 上传到受信源后，再把该 ZIP 的地址和摘要写入清单。清单和 ZIP 不包含本机配置、报告、会话或认证信息。

## 隔离验收

本地验收应使用临时 `YDF_BROWSER_HOME`、临时 skill 根目录和测试 transport，禁止覆盖真实安装目录或提交运行证据。至少验证：成功切换后保留 `current/previous`、摘要或健康检查失败仍指向旧版本、并发只有一个更新任务、显式回滚恢复上一版本。
