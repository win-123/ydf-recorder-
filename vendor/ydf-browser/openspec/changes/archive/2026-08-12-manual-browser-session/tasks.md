## 1. 测试先行

- [x] 1.1 在 `tests/test_cli.py` 增加无 DSL 手工会话的参数门禁、启动顺序、最小 JSON、无报告和 `Ctrl-C` 退出测试
- [x] 1.2 在 `tests/test_runtime.py` 增加首页 Cookie 注入导航、多个标签页保持会话和全部页面关闭结束的测试
- [x] 1.3 运行新增聚焦测试，确认它们因手工会话能力尚未实现而按预期失败

## 2. 浏览器运行时

- [x] 2.1 为 `PlaywrightRuntime` 增加首页导航入口，复用现有 session cookie 注入和 context 级请求转发
- [x] 2.2 为 `PlaywrightRuntime` 增加等待手工会话结束的入口，支持用户创建的多个标签页和 context 已关闭场景
- [x] 2.3 使手工会话结束时的 runtime 清理具备幂等的 best-effort 语义，不影响已有 DSL 运行清理

## 3. CLI 手工会话

- [x] 3.1 在 `run` 的 DSL 编排前增加无 `--dsl` / `--dsl-list` 手工模式分流，并保留显式 DSL 输入路径
- [x] 3.2 实现手工模式参数门禁、环境级 API 登录、profile 生命周期和首页打开顺序
- [x] 3.3 实现浏览器关闭、启动失败和 `Ctrl-C` 的退出码及最小 stdout JSON 语义

## 4. 文档与验证

- [x] 4.1 更新 `README.md` 和请求转发说明，加入手工浏览器会话命令与参数边界
- [x] 4.2 运行聚焦测试、完整 `./.venv/bin/python -m pytest`、`openspec validate manual-browser-session --strict`、`./scripts/check_openspec_language.py --change manual-browser-session` 和 `git diff --check`

## 5. 真实验证修复

- [x] 5.1 修复持久化上下文启动时额外保留空白标签页的问题，并用可见浏览器复验关闭页签后的退出行为
- [x] 5.2 修复手工会话带请求转发时新标签访问非转发地址会阻塞同一会话网络的问题，并用可见浏览器截图复验新标签和系统页签主体均可渲染
