## 1. 回归测试

- [x] 1.1 为运行时页面响应入口增加服务详情、有效模板和模板业务错误捕获测试，并逐项确认 RED
- [x] 1.2 为 `WorkflowExecutor.run(open_menu)` 增加无前置模板请求、有效首屏模板、业务错误、技术错误恢复和 open-only 测试，并逐项确认 RED
- [x] 1.3 为 `open_menu` 新阶段计时增加报告测试并确认旧 `fetch_template_ms` 断言 RED

## 2. 运行时与执行器实现

- [x] 2.1 复用现有页面 response 监听保存当前菜单的服务详情、有效模板和明确业务错误，并在每次 `open_menu` 前清空旧状态
- [x] 2.2 删除真实 `open_menu` 的 `YondifGateway.fetch_template()` 调用，直接打开菜单并在步骤总预算内消费页面实际响应
- [x] 2.3 使用页面服务元数据保持 open-only fail-closed 分类，并让模板技术错误可由后续有效响应恢复
- [x] 2.4 将首屏模板等待改为 `initial_template_wait_ms` 并保持菜单业务稳定耗时、工作面等待和绑定语义

## 3. 验证与文档

- [x] 3.1 运行 executor、runtime、gateway、计时和性能报告聚焦测试及 `git diff --check`
- [x] 3.2 运行 `openspec validate reuse-open-menu-browser-template-response --strict` 和 `./scripts/check_openspec_language.py --change reuse-open-menu-browser-template-response`
- [x] 3.3 使用正常单据菜单真实 DSL 验证页面模板响应、工作面等待和后续组件动作
- [x] 3.4 使用原集中支付 DSL 验证旧前置请求的“支付管理未授权”不再阻断页面实际链路，并以回归测试覆盖页面真实业务错误字段传播
- [x] 3.5 运行完整 `./.venv/bin/python -m pytest` 并复核最终差异没有无关改动
