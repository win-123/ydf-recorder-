## 1. 回归测试

- [x] 1.1 在 `tests/test_runtime.py` 增加 `fill_query_field` 对 `YDFTreeModalSelect` / refer 查询字段走 `_select_popup_reference()` 的单元测试。
- [x] 1.2 在 `tests/test_runtime.py` 增加普通 `YDFTreeSelect` 查询字段仍走 `_select_query_choice()` 的单元测试。
- [x] 1.3 在 `tests/test_executor.py` 增加 `query.search` 对弹出参照查询条件保留标量、列表和结构化 `equals` 原值的执行器测试。
- [x] 1.4 在 `tests/test_executor.py` 增加查询条件弹出参照结果写入步骤报告的测试，覆盖 `selected`、`confirmed`、`confirm_label`、`popup_tree_context`。

## 2. 运行时实现

- [x] 2.1 调整 `ydf_browser/executor.py` 的 `_execute_query_search()`，移除对 `condition["equals"]` 的提前字符串化，仅在报告或 fallback 文本展示时转换。
- [x] 2.2 调整 `ydf_browser/runtime.py` 的 `fill_query_field()`，让 modal/reference 查询字段优先走 `_select_popup_reference()`。
- [x] 2.3 确保 `YDFTableModalSelect` 查询字段沿用 `_ensure_table_reference_target_uses_match()` 的结构化目标约束。
- [x] 2.4 保持文本框、普通下拉和普通树形下拉查询字段的现有行为不变。

## 3. 文档和示例

- [x] 3.1 更新 `skills/gov-ydfdev-browser/references/dsl-reference.md` 中 `query.search` 说明，补充查询条件弹出参照和多选列表写法。
- [x] 3.2 如有合适位置，补充或调整示例 YAML，体现 `项目目录` 查询条件弹出参照的稳定写法。
- [x] 3.3 检查 `schemas/dsl.schema.json` 是否需要补充 query target 约束；如不需要，记录原因并保持现状。
  - Note: 当前 JSON schema 只对 `tree.select` 做细化 target 约束，其他组件 target 保持 generic object；本变更不改 schema，继续以 `ydf_browser/dsl.py` 的运行时校验作为 DSL source of truth。

## 4. 验证

- [x] 4.1 运行聚焦测试：`./.venv/bin/python -m pytest tests/test_runtime.py tests/test_executor.py -q`。
- [x] 4.2 运行 DSL 校验：`./.venv/bin/python -m ydf_browser.cli validate --dsl /Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-预算绩效-YDF-80421-0001.yaml`。
- [x] 4.3 运行 OpenSpec 严格校验：`openspec validate support-query-popup-reference --strict`。
- [x] 4.4 运行格式检查：`git diff --check`。
- [x] 4.5 若具备可用登录上下文，真实执行该 YAML 并确认查询步骤不再误走 dropdown；记录报告路径和结果。
  - Report: `/tmp/ydf-query-popup-reference-report.json`; result `success=true`, run `20260613-152602-3f24ed25`, query step recorded `selected` and `confirm_label=确定`.
