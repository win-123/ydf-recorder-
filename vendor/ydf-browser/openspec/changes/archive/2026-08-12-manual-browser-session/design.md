## Context

当前 `run` 在创建运行报告和加载 suite 前要求 `_dsl_inputs()` 成功，因此没有 DSL 时无法启动浏览器。真实运行已经具备 API 登录、持久化 profile、Cookie 注入、Playwright context 级请求转发和浏览器清理能力；本设计只补充一个不进入 DSL 编排的入口。

## Goals / Non-Goals

**Goals:**

- 复用现有真实运行的环境解析、API 登录、profile 和请求转发语义。
- 在登录成功后打开解析后的 `base_url/`，并将控制权交给开发人员。
- 用 browser context 页面数量作为会话完成信号，支持用户打开的新标签页。
- 让手工会话不创建 DSL 报告，同时保持统一的 CLI 错误输出和用户中断退出码。

**Non-Goals:**

- 不增加新的 CLI 子命令、DSL 动作、租户/组织/年度自动选择或手工操作录制。
- 不保存手工操作期间的网络正文、转发事件或新的报告格式。
- 不改变已有 DSL `run`、`validate`、fixture 和 AI 观察模式。

## Decisions

### 在 `_cmd_run` 进入 DSL 编排前分流

当 `dsl_input_specs` 完全缺失时，CLI 先校验手工模式参数、解析转发规则并加载环境，然后进入手工会话；这样不会创建报告目录、事件记录或触发 DSL 解析。只要存在 `--dsl` 或 `--dsl-list` 参数，就继续走现有 DSL 路径，因此空清单仍由现有 DSL 输入校验报错。

### 保持现有真实运行的登录顺序

持久化 profile 模式先启动 runtime、清除当前目标环境可见 cookies，再执行 API 登录并把新 session 交给 runtime；临时 context 模式先完成 API 登录，再创建浏览器。两条路径均在首页导航前注入 API session cookies，环境级凭据直接来自选定环境。

### 在 runtime 增加首页导航和会话等待边界

`PlaywrightRuntime` 提供两个窄入口：一个负责注入 cookies 后导航到 `base_url/`，另一个轮询当前 context 的页面集合直到为空或 context 已关闭。轮询使用短间隔，避免引入新的异步控制层；context 级 route 已覆盖用户后来创建的页面，因此转发能力不需要复制到每个标签页。

### 用显式参数门禁避免误导

无 DSL 时拒绝 `--headless`、DSL 过滤和变量、fixture、菜单、报告、性能、AI 观察及相关限制参数；接受环境、profile 和转发参数。这样错误命令不会被静默解释成手工会话，也不会产生看似可用但实际没有意义的报告路径。

### 正常关闭和用户中断使用不同结果

首页导航成功后，全部页面关闭是正常退出并输出固定最小 JSON；`KeyboardInterrupt` 执行清理后返回 `130`，不输出成功结果。启动阶段异常继续交给现有主入口输出统一错误 JSON，手工会话自身只负责确保 runtime 清理。

## Risks / Trade-offs

- [Risk] Playwright context 在用户直接关闭浏览器后可能已处于 closed 状态，清理调用可能再次触发 closed 异常 → [Mitigation] 手工等待将 context closed 视为正常会话结束，runtime 清理采用幂等的 best-effort 语义。
- [Risk] 页面集合轮询不是事件驱动，存在最多一个轮询间隔的退出延迟 → [Mitigation] 使用短轮询间隔；当前需求不需要新增异步生命周期抽象。
- [Risk] 持久化 profile 可能被另一个运行占用 → [Mitigation] 沿用 Playwright 启动失败和现有 profile 锁语义，启动失败不进入手工等待。

## Migration Plan

无需数据迁移或配置迁移。实现发布后，旧的带 `--dsl` / `--dsl-list` 命令保持原行为；开发人员可直接省略 DSL 参数使用新模式。回滚只需移除无 DSL 分支及其文档，不影响 profile 内容和既有报告。
