## Why

`ydf-browser run` 目前每个真实用例都使用全新的无缓存浏览器上下文，执行速度慢，也无法模拟测试人员长期使用同一个浏览器 profile、跨环境访问和系统升级后继续工作的真实场景。

业务系统要求用户不需要主动清理浏览器缓存即可在升级后正常使用；默认持久化浏览器 profile 能把这类缓存兼容性问题暴露为真实运行失败，同时保留隔离模式用于复核。

## What Changes

- 默认真实浏览器运行使用 ydf-browser 管理的全局唯一持久化浏览器 profile，不按 `base_url`、用户、租户或默认组织隔离。
- 新增 `--no-persistent-profile`，用于回到当前每个用例临时浏览器上下文的隔离语义。
- 新增 `ydf-browser profile clear`，只清空 ydf-browser 管理的整个持久化浏览器 profile；profile 正在使用时必须失败。
- 持久化浏览器 profile 模式下强制串行执行，不允许 `--concurrency` 大于 1。
- 持久化浏览器 profile 模式下，每个用例在 API 登录前清除当前目标环境可见 cookies，但不清理 localStorage、sessionStorage、IndexedDB、HTTP cache 或 service worker。
- 一次 `run` 复用同一个浏览器实例和持久化 profile；每次 `open_menu` 使用新页面并关闭旧页面；每个用例结束后关闭本轮运行打开的页面。
- 报告记录 profile 模式、profile 路径和 cookies reset 策略，不记录 cookie 或 storage 内容。
- `--performance` 的 cache mode 命名和报告语义同步区分持久化 profile、临时上下文和同用例重新打开菜单。
- fixture 模式和 `validate --dsl` 不受影响。
- 补充 `CONTEXT.md` 术语和 ADR，记录默认持久化 profile 的决策背景。

## Capabilities

### New Capabilities
- `browser-profile-lifecycle`: 定义真实浏览器运行中持久化浏览器 profile、临时浏览器上下文、profile 清空命令、cookies reset、页面生命周期和报告字段的用户可见语义。

### Modified Capabilities
- `performance-xlsx-report`: 更新性能报告中的 cache mode 语义，使默认持久化 profile 后的冷/暖指标名称仍能准确表达执行上下文。

## Impact

- CLI：`run` 默认 profile 模式、`--no-persistent-profile` 参数、`profile clear` 子命令、并发限制和报告元数据。
- 运行时：`PlaywrightRuntime` 的 browser/context/page 生命周期、persistent context 启动、当前目标环境可见 cookies 清理和页面关闭策略。
- 报告与性能导出：JSON、HTML、stdout 摘要和 `performance.xlsx` 中的 profile/cache mode 字段。
- 文档：`CONTEXT.md` 术语、ADR、OpenSpec 主规格归档后的稳定能力语义。
