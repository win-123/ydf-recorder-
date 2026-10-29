## 1. 规划与基线

- [x] 1.1 完成 proposal、design、tasks 和 `CONTEXT.md` 术语，并以 `openspec validate refactor-menu-opening-deep-module --strict`、语言检查及 `git diff --check` 验证。
- [x] 1.2 盘点 `WorkflowExecutor` 与 `PlaywrightRuntime` 的菜单打开状态、调用和测试覆盖，并把迁移清单落实到后续任务。

## 2. 公开 interface 与 fixture vertical slice

- [x] 2.1 在 `tests/test_menu_opening.py` 写首个公开 seam RED，覆盖 fixture 菜单解析、manifest、绑定和不可变成功结果，并确认失败来自缺少 `ydf_browser.menu_opening`。
- [x] 2.2 新增单文件 `ydf_browser/menu_opening.py`，实现 `MenuOpeningRequest`、`MenuOpeningResult`、`MenuOpeningError` 与最小 `MenuOpening.open`，使首个 interface test 变绿。
- [x] 2.3 增加 fixture open-only、菜单承载和失败映射 interface tests，再实现 fixture adapter 路径并验证聚焦测试通过。

## 3. 生产页面响应与初始终态

- [x] 3.1 先补页面实际服务详情和模板响应的 interface RED，再迁移生产响应消费，验证技术错误后成功恢复且不调用 `gateway.fetch_template`。
- [x] 3.2 先补动态工作面、状态转换、500ms 稳定快照和重复根 interface RED，再迁移工作面扫描与终态状态机并验证聚焦测试通过。
- [x] 3.3 先补模板业务错误、工作面业务错误、页面错误与共享期限 interface RED，再迁移结构化 `MenuOpeningError` 证据并验证失败页面不被关闭。
- [x] 3.4 迁移菜单承载、页面状态、绑定和阶段计时，使用 interface tests 验证现有报告字段和值保持兼容。

## 4. 调用者切换与旧 implementation 删除

- [x] 4.1 将 `WorkflowExecutor._handle_open_menu` 收窄为请求构造、结果接收和 `StepResult` 映射，并以 executor 聚焦测试验证当前状态及 `OpenMenuCompletionError` 报告类型兼容。
- [x] 4.2 删除 executor 的菜单打开私有轮询、模板消费和兼容分支，并以 `rg` 与聚焦测试确认只经 `MenuOpening.open` 执行。
- [x] 4.3 删除 runtime 的菜单专属可变 payload 和已迁移语义，保留 profile page 交接、cookies、导航、页面求值和事件捕获 adapter 职责，并运行 runtime 聚焦测试。
- [x] 4.4 删除或改写被 interface tests 替代的私有实现测试，确认 runtime/executor tests 只覆盖各自 interface 职责且 `git diff --check` 通过。

## 5. 验证与交付

- [x] 5.1 运行 `./.venv/bin/python -m pytest -q tests/test_menu_opening.py` 及相关 executor/runtime 聚焦测试。
- [x] 5.2 运行完整 `./.venv/bin/python -m pytest -q`，修复全部回归。
- [x] 5.3 使用当前源码运行 `tests/real_cases/open_menu_browser_template_response.yaml`，检查页面实际模板响应、manifest、初始工作面、绑定和表格断言。
- [x] 5.4 使用当前源码运行 `tests/real_cases/pay_contract_audit_initial_query_readiness.yaml`，检查页面级加载遮罩结束前不放行且后续查询和表格断言通过。
- [x] 5.5 运行 `openspec validate refactor-menu-opening-deep-module --strict`、`./scripts/check_openspec_language.py --change refactor-menu-opening-deep-module` 和 `git diff --check`，完成最终交付检查。
