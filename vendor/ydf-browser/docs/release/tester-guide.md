# ydf-browser 测试人员指南

本指南面向运行已准备好的 YAML 测试集并查看报告的测试人员。

## 安装

安装前确认当前用户可使用 Python 3.11 或更高版本。发布负责人将 `<公司内部域名>` 替换为实际 HTTPS 地址后，macOS 或 Linux 使用：

```bash
curl -qfsSL "https://<公司内部域名>/ydf-browser/install.sh" | sh
ydf-browser doctor
```

Windows PowerShell：

```powershell
irm "https://<公司内部域名>/ydf-browser/install.ps1" | iex
ydf-browser doctor
```

引导安装器会查询 stable 发布清单，校验发布包地址、SHA-256 和解压路径后，在用户目录下创建独立 runtime。它不会自动安装 Python、修改 shell profile、询问业务凭据或覆盖已有配置；重复执行同一命令会重新安装当前 stable 版本。如果发布负责人没有内置完整的平台依赖 `wheels/` 缓存，安装过程可能需要访问公司的 Python 包镜像和 Playwright 浏览器镜像。

默认命令入口位于 macOS/Linux 的 `~/.local/bin` 或 Windows 的 `~/.ydf-browser/bin`。Windows 安装器会将实际命令目录去重加入当前用户 `PATH`；使用 `irm | iex` 时同一 PowerShell 窗口可立即执行命令，使用 `powershell -File` 时后续登录会话生效。macOS/Linux 仍按安装结果提示手工处理 `PATH`。

引导安装器只安装 runtime。后续需要安装同版本 skill 时，在 macOS、Linux 或 Windows 执行：

```bash
ydf-browser install-skill
```

完整 skill 只安装到 `${AGENTS_HOME:-~/.agents}/skills/gov-ydfdev-browser`。Codex 直接使用该规范副本，Claude Code 使用指向它的链接，不会额外创建 `.codex/skills` 副本。

无法访问引导安装器时，可以手工下载并解压发布包，在包目录运行 `./scripts/install-runtime.sh` 或 `.\scripts\install-runtime.ps1`。

安装版默认在每次命令启动时按 24 小时冷却周期后台检查 runtime 更新。检查和安装不打断正在运行的用例；成功后下一次命令使用新版本。需要查看或控制更新时使用：

```bash
# 立即检查并安装更高 stable runtime
ydf-browser update

# 只检查，不安装
ydf-browser update --check

# 回滚到上一保留 runtime
ydf-browser update rollback

# 只关闭后台自动更新；显式 update 仍可用
YDF_BROWSER_AUTO_UPDATE=0 ydf-browser doctor
```

更新状态会出现在 `ydf-browser doctor` 的 `checks.update` 中。显式 update 绕过 24 小时冷却，但只安装更高 stable runtime；当前命令不会自重启，下一次命令才使用新版本。更新失败不代表当前 runtime 不可用；配置、`env.local.yaml`、浏览器 profile、报告和 skill 安装目录不会被自动更新覆盖。skill 由 `ydf-browser install-skill` 独立更新。

## 命令帮助

需要查看参数用途、默认值或组合限制时，直接使用命令行帮助：

```bash
ydf-browser --help
ydf-browser run --help
ydf-browser validate --help
```

直接执行 `ydf-browser` 或使用 `--help` 都是本地帮助查询，不需要登录或启动浏览器；完整参数说明以对应命令的 `--help` 输出为准。

## 配置

runtime 安装器会创建可编辑配置文件：

```bash
~/.ydf-browser/config/env.yaml
```

在这里填写真实环境地址、用户名和密码。密码只保存在你自己的机器上。同目录可选的 `env.local.yaml` 会作为本机覆盖文件参与合并；没有这个文件时，`env.yaml` 中的配置也会完整生效。只有需要多个业务账号或 BPR 原始报告时，才需要额外配置 `users` 或 `bpr`。

普通场景不需要配置 `users`，工具会用环境级 `username/password` 自动合成 DSL 默认用户。只有需要多个业务账号时，才在 `users` 中增加中文别名，例如 `审核岗`；空对象别名会继承环境级账号。BPR 原始报告下载需要配置独立的 `bpr.username/password`，两项必须同时配置，不能回退使用业务账号。

YAML 测试集必须提供 `suite.tenant`，并提供 `suite.default_org` 或 `cases[].default_org`。

## 运行

```bash
ydf-browser run --dsl examples/project_suggest_tabs.yaml --headless
```

如果需要按人工清单顺序批量运行多个 DSL，可以准备一个文本文件，一行写一个 DSL 文件：

```text
# suites.txt
examples/payment_contract_registration_tabs.yaml
examples/project_suggest_tabs.yaml
```

```bash
ydf-browser validate --dsl-list suites.txt
ydf-browser run --dsl-list suites.txt --headless
```

清单中的相对路径按清单文件所在目录解析，空行和 `#` 注释行会被忽略。`--dsl-list` 表示存在前后依赖的严格串行执行链，不能同时设置 `--concurrency` 大于 `1`。

`validate` 和 `run` 的执行前校验会检查全部展开后的 DSL 文件，按输入顺序一次性汇总各文件的错误；任一文件失败时，`run` 不会执行业务用例。终端显示实际出错文件及错误详情，JSON 摘要的 `validation_errors` 数组包含各文件的 `dsl_file` 和 `message`；`run` 的 JSON、HTML 报告也会逐文件记录失败。变量错误同时显示字段路径，例如 `cases[1].steps[2].target.conditions[1].equals`，下标从 1 开始；YAML 解析错误保留行号和列号。单个文件内部沿用现有校验规则，不保证穷举其全部错误。

默认真实运行会使用 ydf-browser 管理的持久化浏览器 profile，模拟测试人员长期使用同一个浏览器访问多个环境。每个用例安装当前账号已验证的 cookies，不清理 localStorage、IndexedDB、HTTP cache 或 service worker。

真实 DSL 运行默认按规范化后的实际 `base_url + username` 复用认证会话，配置别名不影响身份。每例先探测身份并校验租户、组织和年度；有效时不重新提交密码。同一本机会话目录内，同身份用例全程串行。会话保存在 `<YDF_BROWSER_HOME>/sessions/`（默认 `~/.ydf-browser/sessions/`），属于敏感登录态，不应分享或提交。

准备阶段收到 `401`，或重定向到同源的 `/login`、`/cas/login`、`/login_light` 时，工具会按认证失效处理，按需废弃旧会话并最多重新认证一次。其他跳转、网络错误和权限拒绝仍会阻断准备，不自动提交密码。cookie 没有客户端过期时间也不代表服务端认证仍有效；重新认证后仍要求登录时，不进入业务步骤。

无 DSL 的手工浏览器会话也使用同一认证缓存，关闭后立即重开且认证有效时不会再次登录或发送短信。手工会话保留当前租户、组织和年度，整个操作期间持有账号锁；浏览器关闭时保存最后可读取的 cookies 快照，下次启动仍须探测。需要重新认证可运行 `ydf-browser run --env <环境名> --force-login`。

需要重新认证时使用 `run --force-login`：本次命令每个身份首次使用时重新登录，后续用例仍复用。`--no-persistent-profile` 和 `profile clear` 只影响浏览器状态，不清除独立会话缓存、不强制登录。执行中失效按原失败策略处理，不自动重放动作；下一用例再探测。此阶段不包含自动短信验证，报告中的 `password_login_count` 是密码认证次数，不是短信次数。

如果怀疑失败和长期浏览器状态有关，可以用临时浏览器上下文复核：

```bash
ydf-browser run --dsl examples/project_suggest_tabs.yaml --headless --no-persistent-profile
```

需要并行执行彼此独立的 case 时，可以设置全局最大并发数：

```bash
ydf-browser run --dsl examples --headless --no-persistent-profile --concurrency 2
```

`--concurrency` 默认为 `1`，且必须大于等于 `1`。使用时注意：

- 默认持久化浏览器 profile 不支持大于 `1` 的并发；并发真实用例必须使用 `--no-persistent-profile`。
- `--dsl-list` 用于有前后依赖的严格串行执行链，不能与大于 `1` 的并发值同时使用。
- 运行期变量 suite 以及使用 `stop_suite`、`stop_run` 失败策略的相关 suite 仍会串行。
- 并发只发生在 case 之间，单个 case 内的 steps 保持顺序执行；并发 case 的完成顺序不固定。
- 多个 case 会修改同一业务数据时不要并发，真实环境建议先使用 `--concurrency 1`。

当报告和静态诊断文件不足以判断系统、DSL 或工具问题时，可以保留首个失败页面供人工核对：

```bash
ydf-browser run --dsl examples/project_suggest_tabs.yaml --pause-on-failure
```

该参数只支持交互式、可见、串行的普通真实 DSL 运行；不能同时使用 fixture、`--headless`、`--concurrency` 大于 `1`、`--ai-observe`、`--performance` 或显式的 `continue`/`stop_suite` 失败策略。失败后工具停止整次运行，在 stderr 提示失败上下文，并保持页面可操作；检查完成后可按 Enter，也可直接关闭失败页签或整个浏览器，工具随后写入失败报告并返回非零退出码。`report.timing.failure_pause` 记录人工等待，`ended_by` 为 `enter` 或 `browser_closed`；暂停期间的手工操作不属于 DSL 证据。Ctrl-C 返回 `130`，不保证完整报告。

如果需要人工兜底清空 ydf-browser 管理的整个持久化浏览器 profile：

```bash
ydf-browser profile clear
```

命令会向 stdout 输出精简 JSON 摘要。完整详情在：

- `report.json`
- `report.html`
- `events.jsonl`
- `artifacts/`：失败截图和诊断文件

## 反馈问题前

先运行：

```bash
ydf-browser doctor
ydf-browser validate --dsl path/to/suite.yaml
```

反馈时请附上执行命令、`report.html` 和 `report.json`。
