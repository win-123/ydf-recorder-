## Context

默认持久化 profile 在一个 run 内复用同一个 Playwright `BrowserContext`。当前 `close_case_pages()` 会先关闭 context 中全部 page，下一用例再调用 `context.new_page()`；`_replace_page_for_menu()` 也先关闭旧 page，再创建新 page。macOS Chromium 允许 persistent context 暂时没有 page，但多台 Windows 电脑在原 DSL 上均表现为最后一个 page 关闭后 context 随之失效，下一用例稳定报 `BrowserContext.new_page: Target page, context or browser has been closed`。

原用例第一条完整通过，第二条单独运行通过，增加 `--no-persistent-profile` 后整个测试集通过，因此无需修改 DSL、业务数据、登录或页面绑定。

## Goals / Non-Goals

**Goals:**

- 持久化 profile 的共享 context 在跨用例清理和菜单 page 替换期间始终至少保留一个可用 page。
- 关闭上一用例产生的全部业务 page，不把页面状态泄漏到下一用例。
- 用平台无关、可稳定变红的生命周期测试模拟 Windows 零 page 行为，并用原 DSL 在 Windows 上做最终真实验证。

**Non-Goals:**

- 不修改临时浏览器上下文模式。
- 不增加 context 异常关闭后的自动重启或静默重试；浏览器真实崩溃仍应直接报告失败。
- 不修改 `去签章`、资金补录或其他业务页面专用逻辑。
- 不新增 DSL 字段、命令行参数或第三方依赖。

## Decisions

### 1. 先创建接替 page，再关闭旧 page

所有持久化 context 的 page 交接都采用同一顺序：先通过现有 `_new_page()` 创建并安装事件监听的接替 page，再关闭交接前快照中的旧 page，最后更新 `_page`。这同时覆盖用例结束清理和 `open_menu` 替换，确保交接过程不会出现零 page 窗口。

未采用“关闭后发现 context 失效再重启”，因为它会掩盖真实浏览器崩溃，还会重复登录、profile 初始化和事件监听。未采用 Windows 条件分支，因为生命周期约束应对所有平台一致。

### 2. 用 run-scope 空白 page 隔离用例

用例结束时创建的接替 page 只作为共享 runtime 的 run-scope holder，不承载上一用例业务状态。清理只关闭交接前已存在的 page；下一次 `open_menu` 再以相同的先建后关顺序把 holder 替换为业务 page。整个 run 结束仍由 `runtime.stop()` 关闭 context 和剩余 page。

未采用保留上一用例最后一个业务 page，因为它会把页面脚本、弹窗和运行状态带到下一用例，不符合页面隔离要求。

### 3. 回归测试模拟零 page 即关闭的 context

扩展最小 fake context，使其在最后一个 page 被关闭时标记 context 已关闭，之后 `new_page()` 抛出与 Windows 报告一致的错误。回归测试必须证明 `close_case_pages()` 和连续 `open_menu` 的任何交接时刻 page 数均不为零，并且下一用例仍可创建业务 page。

这种测试比只在 macOS 启动真实 Chromium 更能稳定捕获跨平台缺陷；最终验收仍要求同事在 Windows 使用原失败 DSL 验证持久化模式通过。

## Risks / Trade-offs

- [Risk] page 交接时会短暂同时存在新旧两个 page → 只对交接前快照执行关闭，接替 page 不进入清理集合，并用测试固定顺序。
- [Risk] 新建 holder page 触发已有网络、console 和 page error 监听 → 复用 `_new_page()` 的统一监听安装，不新增第二套 page 创建路径。
- [Risk] context 已因真实崩溃关闭时创建接替 page 仍会失败 → 保留原始异常并让用例失败，不做可能掩盖故障的恢复。
- [Trade-off] 每个用例边界多创建一个空白 page → 这是一次本地轻量操作，换取 Windows persistent context 的稳定复用。
