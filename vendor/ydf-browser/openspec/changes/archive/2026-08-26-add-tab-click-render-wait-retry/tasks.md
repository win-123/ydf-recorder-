## 1. 单元测试先行（TDD）

- [x] 1.1 在 `tests/test_runtime.py` 中新增测试用例：`_resolve_visible_tab_action` 在元素已渲染时首次命中即返回，验证不引入额外延迟（验证方式：`./.venv/bin/python -m pytest tests/test_runtime.py -k "tab_action_already_rendered" -q` 通过）。
- [x] 1.2 在 `tests/test_runtime.py` 中新增测试用例：使用 `unittest.mock.patch` 模拟 `_find_first_visible_selector` 前两次返回 None、第三次返回有效选择器，验证轮询重试在超时内命中（验证方式：`./.venv/bin/python -m pytest tests/test_runtime.py -k "tab_action_retry_hit" -q` 通过）。
- [x] 1.3 在 `tests/test_runtime.py` 中新增测试用例：模拟所有选择器在超时内始终返回 None，验证抛出 `RuntimeError` 且错误消息包含 fieldid 匹配计数和 stepBar 容器状态（验证方式：`./.venv/bin/python -m pytest tests/test_runtime.py -k "tab_action_retry_exhausted" -q` 通过）。

## 2. 运行时实现

- [x] 2.1 在 `ydf_browser/runtime.py` 的 `PlaywrightRuntime` 类中新增私有方法 `_collect_tab_diagnostic(self, fieldid: str | None, action_label: str) -> str`，按设计 D3 的格式返回诊断字符串（验证方式：`./.venv/bin/python -c "from ydf_browser.runtime import PlaywrightRuntime; print(hasattr(PlaywrightRuntime, '_collect_tab_diagnostic'))"` 输出 True）。
- [x] 2.2 修改 `_resolve_visible_tab_action` 方法：将现有单次选择器遍历包装在 `time.monotonic()` 计时的轮询循环中（间隔 500ms、超时 5000ms），首轮命中立即返回，后续轮次重试 fieldid 和兜底选择器（验证方式：`./.venv/bin/python -c "import inspect; from ydf_browser.runtime import PlaywrightRuntime; src = inspect.getsource(PlaywrightRuntime._resolve_visible_tab_action); assert 'monotonic' in src and 'retry' in src.lower()"` 不抛异常）。
- [x] 2.3 修改 `click_tab_action` 方法的 `except RuntimeError` 分支：调用 `_collect_tab_diagnostic` 将增强诊断拼接到错误消息（验证方式：`./.venv/bin/python -m pytest tests/test_runtime.py -k "tab_action_retry_exhausted" -q` 通过且错误消息包含 `stepBar`）。

## 3. 集成验证

- [x] 3.1 运行聚焦测试套件确认无回归（验证方式：`./.venv/bin/python -m pytest tests/test_runtime.py -q` 全部通过）。
- [x] 3.2 运行完整测试套件确认无意外破坏（验证方式：`./.venv/bin/python -m pytest -q` 全部通过）。
- [x] 3.3 使用真实 DSL 用例验证：在 `/Users/huangzy/Workspace/work/yonyougov/ydf-browser-问题用例/10流程-预算执行-采购管理-采购计划新增审核-正向-0001` 目录执行 `HEADLESS=1 ./.venv/bin/ydf-browser run --dsl-list case.list --config ./env.yaml --env ydf --no-persistent-profile --headless --report-dir ./reports`，连续运行 3 次确认 case 1 和 case 2 全部通过且无 tab.click 失败。

## 4. 文档与规格检查

- [x] 4.1 运行 `openspec validate add-tab-click-render-wait-retry --strict` 确认结构校验通过。
- [x] 4.2 运行 `./scripts/check_openspec_language.py --change add-tab-click-render-wait-retry` 确认语言检查通过。
- [x] 4.3 运行 `git diff --check` 确认无空白错误。
