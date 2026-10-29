## 1. 测试先行

- [x] 1.1 为 profile 路径解析、`YDF_BROWSER_PROFILE_DIR` 覆盖和默认 `<YDF_BROWSER_HOME>/browser-profile/default` 增加聚焦测试。
- [x] 1.2 为当前目标环境可见 cookies 匹配增加单元测试，覆盖 host cookie、父域 cookie、无关域 cookie 和 path 不匹配 cookie。
- [x] 1.3 为 `run` 默认持久化、`--no-persistent-profile` 回退、持久化模式拒绝 `--concurrency > 1` 增加 CLI 测试。
- [x] 1.4 为 `profile clear` 成功删除、profile 锁定时失败和不提供细粒度清理增加 CLI 测试。
- [x] 1.5 为每次 `open_menu` 新 page、关闭旧 page、用例结束关闭本轮 pages 增加 runtime 或 executor 聚焦测试。
- [x] 1.6 为报告 profile metadata 和 performance cache mode 新语义增加 JSON/HTML/XLSX 相关测试。

## 2. Profile 生命周期实现

- [x] 2.1 在 CLI 层增加 `--no-persistent-profile` 和 `profile clear` 命令，保持 fixture 模式和 `validate --dsl` 不读取 profile。
- [x] 2.2 实现最小 profile 路径解析和 profile 清空逻辑，清空时检测运行中或锁定状态并给出明确错误。
- [x] 2.3 调整真实运行调度：默认持久化 profile 模式强制 `--concurrency=1`，`--no-persistent-profile` 保留现有并发语义。
- [x] 2.4 调整 `PlaywrightRuntime` 支持持久化 context 启动和临时 context 回退，避免复用用户真实 Chrome profile。
- [x] 2.5 在 API 登录前清除当前目标环境可见 browser cookies，并保留 storage/cache/service worker。
- [x] 2.6 将一次 `run` 的 browser/profile 复用接入真实用例执行链路，保留现有 API 登录、租户、默认组织、业务年度和菜单解析顺序。
- [x] 2.7 调整 `open_menu` 页面生命周期：每次新建 page、关闭旧 page，用例结束关闭本轮打开的 pages。

## 3. 报告、性能和文档

- [x] 3.1 在结构化报告、stdout 摘要和 HTML 报告中输出 profile mode、profile path 和 cookies reset 策略，不输出 cookie/storage/cache 内容。
- [x] 3.2 更新 `--performance` cache mode 输出，区分 `persistent_profile_case_open_menu`、`persistent_profile_same_case_reopen_menu`、`ephemeral_case_open_menu` 和 `ephemeral_same_context_reopen_menu`。
- [x] 3.3 更新 `performance.xlsx` 导出和汇总逻辑，使工作簿保留新的 cache mode 语义。
- [x] 3.4 更新用户可见文档或示例，说明默认持久化 profile、`--no-persistent-profile`、`profile clear` 和失败复核方式。

## 4. 验证

- [x] 4.1 运行 `openspec validate default-persistent-browser-profile --strict`。
- [x] 4.2 运行 `./scripts/check_openspec_language.py --change default-persistent-browser-profile`。
- [x] 4.3 运行相关聚焦 pytest，覆盖 CLI、runtime、报告和 performance 导出。
- [x] 4.4 使用至少一个真实 DSL 证明默认持久化 profile 模式可以打开菜单并执行用例。
- [x] 4.5 使用同一个真实 DSL 加 `--no-persistent-profile` 证明隔离回退仍可执行。
- [x] 4.6 准备交付前运行完整 `./.venv/bin/python -m pytest` 和 `git diff --check`。
