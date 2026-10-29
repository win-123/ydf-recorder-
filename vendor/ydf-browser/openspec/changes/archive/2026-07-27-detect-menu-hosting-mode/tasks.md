## 1. 聚焦回归测试

- [x] 1.1 在 `tests/test_runtime.py` 先增加菜单承载方式分类测试，覆盖唯一业务一级 frame、无业务 frame、`helper_iframe-*` 排除、嵌套 frame 排除、多个冲突候选和检查异常。
- [x] 1.2 在 `tests/test_executor.py` 增加 `open_menu` 结果测试，证明 `iframe`、`direct` 和 `unknown` 均写入结构化结果与成功消息，且不改变菜单打开成功状态。
- [x] 1.3 在报告聚焦测试中证明 HTML 成功步骤能够展示菜单承载方式。

## 2. 最小实现

- [x] 2.1 在 `ydf_browser/runtime.py` 的共享运行时入口实现一级业务 frame 与 `MenuTarget` 身份匹配，返回 `mode`、frame 证据或 `unknown` 原因。
- [x] 2.2 在 `ydf_browser/executor.py` 的 `open_menu` 流程接入检测结果，复用现有 `menu_target`、步骤 `data` 和成功消息，不改变模板支持及组件级动作语义。
- [x] 2.3 更新 `README.md` 的 `open_menu` 与报告说明，记录自动识别结果、三种状态和不改变打开成功语义的边界。
- [x] 2.4 在 `CONTEXT.md` 增加“菜单承载方式”领域术语。

## 3. 验证

- [x] 3.1 运行菜单承载方式相关聚焦 pytest，确认新增测试和相邻 `open_menu` 行为通过。
- [x] 3.2 使用当前源码运行包含“交易类型参数设置”和“应用平台>>规则管理>>规则管理>>规则管理”的真实 DSL，确认 JSON/HTML 分别报告 `iframe` 和 `direct`，且两个 `open_menu` 均成功。
- [x] 3.3 运行完整 `./.venv/bin/python -m pytest`、`openspec validate detect-menu-hosting-mode --strict`、`./scripts/check_openspec_language.py --change detect-menu-hosting-mode` 和 `git diff --check`。
