## 1. 回归用例

- [x] 1.1 在 `tests/test_dsl.py` 增加或确认 `popup_reference.select target.match.contains` 可通过 DSL 校验并保留原始结构。
- [x] 1.2 在 `tests/test_runtime.py` 增加运行时单测，覆盖 `_click_popup_reference_table_row()` 可用 `match.contains` 命中目标列候选行。
- [x] 1.3 在 `tests/test_runtime.py` 增加诊断单测，覆盖 `match.contains` 失败时 `row_debug.wantedValue` 使用 contains 值而不是空字符串。
- [x] 1.4 如实现抽取了公共 helper，补充 `matches` / `selections` 或表单结构化参照入口的轻量回归，证明这些入口不会绕过 contains 解析。

## 2. 运行时实现

- [x] 2.1 在 `ydf_browser/runtime.py` 统一弹出参照表格行匹配目标解析，读取 `equals/value/text/label/contains` 并保留匹配模式。
- [x] 2.2 调整 `_click_popup_reference_table_row()`，让 `match.contains` 在指定列或行文本中执行包含匹配，并保持既有 `match.equals` 行为兼容。
- [x] 2.3 调整 `_collect_popup_reference_table_match_debug()`，让诊断采样、`wantedValue` 和错误上下文支持 `match.contains`。
- [x] 2.4 确认 `_popup_reference_target_value()`、`_popup_reference_filter_text()` 等辅助函数不会把 `contains` 误当作过滤条件，避免改变 `filter.conditions[].equals` 行为。

## 3. 真实用例验证

- [x] 3.1 使用当前源码运行 `./.venv/bin/python -m ydf_browser.cli validate --dsl /Users/ken/temp/ydf-browser-问题反馈/监督检查方案1.yaml`，确认 DSL 仍通过。
- [x] 3.2 使用当前源码运行 `./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/监督检查方案1.yaml --headless --report-file /tmp/ydf-supervision-plan-contains-report.json`。
- [x] 3.3 检查真实报告，确认用例至少越过原第 6 步 `popup_reference.select`，并记录后续若失败的独立原因。

## 4. 门禁

- [x] 4.1 运行聚焦单测，例如 `./.venv/bin/python -m pytest tests/test_runtime.py tests/test_dsl.py -k "popup_reference or contains"`。
- [x] 4.2 运行 `openspec validate support-popup-reference-match-contains --strict`。
- [x] 4.3 运行 `openspec validate --all --strict`。
- [x] 4.4 运行项目全量测试 `./.venv/bin/python -m pytest`，全部通过后再报告完成。
