## 1. 复现与测试护栏

- [x] 1.1 用问题 YAML 复现 `YDFDateRange` 外层节点假确认，并记录 `对账起止日期` 的绑定字段、运行时 selector、保存必填错误。
- [x] 1.2 新增 `tests/test_runtime.py` 单测，证明 `YDFDateRange` 不得走普通 `_set_date_field_value` 外层属性写入路径。
- [x] 1.3 新增 `tests/test_runtime.py` 单测，覆盖 `2026-01-01~2026-01-12` 和 `2026-01-01 ~ 2026-01-12` 的解析、录入和归一化报告。

## 2. Runtime 支持

- [x] 2.1 在 `fill_form_field()` 中把 `YDFDateRange` 分支放在普通 `YDFDatePicker` 分支之前。
- [x] 2.2 实现日期范围解析和归一化，非法格式失败并报告字段名与目标值。
- [x] 2.3 实现日期范围真实录入，优先使用目标字段根、`_input`、`_suffix` 打开当前前景日期范围面板，再选择开始日期和结束日期。
- [x] 2.4 实现日期范围真实确认，禁止只读回 runtime 自写的外层 `value/title` 作为成功条件。

## 3. 真实用例与文档

- [x] 3.1 更新或新增稳定样例，保留推荐 DSL 写法 `对账起止日期: "2026-01-01~2026-01-12"`。
- [x] 3.2 用问题 YAML 跑真实保存链路，证明不再因为 `对账起止日期` 为空而失败。
- [x] 3.3 视用户可见行为影响更新 `docs/action-capability-test-plan.md` 或 release tester 文档中的日期范围说明。

## 4. 验证

- [x] 4.1 运行 `openspec validate support-form-date-range-entry --strict`。
- [x] 4.2 运行 `./scripts/check_openspec_language.py --change support-form-date-range-entry`。
- [x] 4.3 运行相关聚焦测试和 `./.venv/bin/python -m pytest`。
