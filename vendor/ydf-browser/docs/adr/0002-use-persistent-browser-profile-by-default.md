# 默认使用持久化浏览器 profile

`ydf-browser` 最初每个真实用例都启动全新的浏览器上下文。这种隔离方式便于排查单个用例，但和测试人员人工使用 YonDiF 的方式不一致：测试人员通常长期使用同一个浏览器 profile，在同一个 profile 中访问多个环境，并且系统升级后不会主动清理浏览器缓存。

我们决定将真实运行的默认模式改为使用 `ydf-browser` 管理的全局唯一持久化浏览器 profile。这个 profile 不按 `base_url`、用户、租户、默认组织或业务年度拆分，因为跨环境和长期残留本身就是需要验证的真实使用场景。若默认持久化模式失败而临时浏览器上下文模式通过，这通常说明问题和长期浏览器状态、前端缓存或旧上下文残留有关。

API 登录仍然是 `ydf-browser` 的事实登录链路。认证策略由 [ADR 0018](0018-reuse-authenticated-sessions-by-runtime-identity.md) 更新：每例获取并探测当前身份会话，按需切租户、组织和年度，校验后安装 cookies；运行中的更新和删除回写当前身份缓存。运行时不清理 localStorage、sessionStorage、IndexedDB、HTTP cache 或 service worker，因为这些状态正是持久化 profile 要保留并验证的内容。

持久化 profile 模式必须串行执行。并发复用同一个 profile 不是测试人员的正常单浏览器行为，会让页签、下载、通知、cookies 和 storage 互相污染。若未来需要并发性能，应单独设计每个 worker 一个 profile 的模式，而不是让多个用例共享同一个 profile 并发运行。

我们保留 `--no-persistent-profile` 作为隔离复核开关，使真实运行可以回到每个用例使用临时浏览器上下文的旧语义；同时提供 `ydf-browser profile clear` 清空 `ydf-browser` 管理的整个持久化 profile。清空命令是人工兜底，不作为默认运行的一部分。
