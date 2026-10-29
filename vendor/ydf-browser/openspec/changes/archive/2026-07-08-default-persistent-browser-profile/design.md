## Context

当前真实运行路径在每个用例中重新 API 登录、创建 `PlaywrightRuntime`、启动 Chromium、创建新的 browser context 和 page，执行结束后关闭整个 runtime。这个模型隔离性强，但每个用例都丢弃 HTTP cache、storage、IndexedDB、service worker 和浏览器进程状态，执行慢，也不能模拟测试人员长期使用同一个浏览器 profile 的真实场景。

业务系统的目标是升级后不要求用户主动清理浏览器缓存。因此，默认执行语义应能暴露长期 profile、跨环境访问和旧前端上下文残留带来的系统问题，而不是每个用例都从全新 context 开始。

## Goals / Non-Goals

**Goals:**
- 默认真实运行使用全局唯一的 ydf-browser 持久化浏览器 profile。
- 保留 `--no-persistent-profile`，用于回到当前每个用例临时浏览器上下文语义。
- 提供 `ydf-browser profile clear` 清空 ydf-browser 管理的持久化 profile。
- 持久化模式下保留 API 登录链路，只在 API 登录前清当前目标环境可见 browser cookies。
- 一次 `run` 复用 browser/profile；每次 `open_menu` 使用新 page，并关闭旧 page；用例结束关闭本轮打开的 pages。
- 报告和性能输出能明确区分 profile 模式、cookies reset 和 cache mode。

**Non-Goals:**
- 不支持复用用户真实 Chrome profile。
- 不按 `base_url`、用户、租户、默认组织或业务年度拆分默认 profile。
- 不在首版支持持久化 profile 并发执行或每个 worker 一个 profile。
- 不提供只清 cookies、只清 storage、只清 HTTP cache 的细粒度清理命令。
- 不改变 fixture 模式和 `validate --dsl`。

## Decisions

### Decision: 默认全局唯一持久化 profile

默认 profile 路径为 `<YDF_BROWSER_HOME>/browser-profile/default`，可通过 `YDF_BROWSER_PROFILE_DIR` 覆盖。默认不按环境或用户拆分，因为人工测试就是在同一个浏览器 profile 中访问多个环境；跨环境残留失败应被视为有价值的系统兼容性信号。

替代方案是按 `base_url` 或用户拆分 profile。它能降低误判，但会绕开本次要验证的真实长期 profile 场景。

### Decision: API 登录仍是事实登录链路

用例开始时，运行时先清当前目标环境可见 browser cookies，再走现有 API 登录、切租户、设置默认组织、必要时重新登录、校验用户上下文、切业务年度和菜单解析链路，最后注入最终 API session cookies 并打开菜单。

替代方案是在浏览器中依赖旧登录态或模拟 UI 登录。它更接近人工点击，但会重写 ydf-browser 当前稳定的登录边界，增加不必要的变更面。

### Decision: 清 cookies，不清 storage/cache

清理范围仅限当前目标环境可见 cookies，避免旧 cookies 和新 API cookies 混合发送。不清 localStorage、sessionStorage、IndexedDB、HTTP cache 或 service worker，因为这些状态是持久化 profile 要验证的对象。

替代方案是完全不清 browser cookies。它能覆盖更极端的旧新 cookies 共存场景，但和 ydf-browser 每个用例按配置用户显式登录的语义冲突，失败后更难判断。

### Decision: 持久化模式强制串行

持久化 profile 模式下 `--concurrency` 大于 1 必须失败。多个用例并发共用同一个 profile 会制造非人工场景的页签、下载、通知、cookies 和 storage 污染。

替代方案是每个 worker 一个 profile。它可以兼顾并发性能，但需要额外 profile 管理和报告语义，不属于首版必要能力。

### Decision: open_menu 新 page，旧 page 关闭

每次 `open_menu` 都创建新 page，并将 runtime 当前 page 切换到新 page；如果已有当前 page，先关闭旧 page。用例结束时兜底关闭本轮打开的所有 pages，但保留 browser/context/profile。

替代方案是保留多个 page。它更像用户多标签页，但会让组件级动作、通知监听、下载事件和性能归因复杂化。

## Risks / Trade-offs

- 持久化 profile 默认后，某些旧用例可能暴露真实系统缓存兼容问题而失败。缓解方式是报告 profile mode/path/cookies reset，并保留 `--no-persistent-profile` 复核。
- profile clear 删除目录时如果 browser 正在使用，可能破坏 profile。缓解方式是检测运行中或锁定状态，失败并提示先结束 run。
- cookie 可见性匹配如果实现过窄，会留下父域 cookie；过宽则可能清掉无关环境 cookie。缓解方式是按浏览器 domain/path 对当前 `base_url` 的可见性建模，并补单元测试。
- performance cache mode 改名会影响依赖旧字段值的报告消费方。缓解方式是在同一变更中更新 JSON/HTML/XLSX 和测试，必要时保留旧字段的兼容读法但输出新语义。
