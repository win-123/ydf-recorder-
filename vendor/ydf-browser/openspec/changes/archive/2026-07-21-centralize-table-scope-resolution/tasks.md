## 1. 表格作用域 module

- [x] 1.1 在 `tests/test_table_scope.py` 先写失败测试，覆盖 hard fieldid、唯一候选、前景硬作用域、必需列和完整候选诊断
- [x] 1.2 新增 `ydf_browser/table_scope.py` 的最小不可变请求、候选、解析结果、错误和 resolver interface，使 1.1 测试通过
- [x] 1.3 为每步刷新、执行前令牌失效和最多一次无副作用重试补失败测试与最小实现

## 2. 主表动作迁移

- [x] 2.1 先为 `table_row_selection.select` 补统一作用域、复合匹配列预校验和禁止 runtime 二次兜底的失败测试，再迁移 executor/runtime 使其通过
- [x] 2.2 先为 `table.assert_columns`、`table.assert_column_values`、`table.assert_row_values` 补必需列与 `absent` 例外测试，再迁移断言路径使其通过
- [x] 2.3 先为 `table_row_action.click` 和 `table.click_cell_link` 补多表格歧义、链接列预校验和作用域证据测试，再迁移动作路径使其通过

## 3. 可编辑表格迁移

- [x] 3.1 先为 `editable_table.add_row` 补前景目标、作用域限定验证和失效重试测试，再迁移新增行路径使其通过
- [x] 3.2 先为 `editable_table.fill_row` 补全部字段列预校验、禁止部分录入和父表头歧义测试，再迁移录入路径使其通过
- [x] 3.3 先为同一 fieldid 拆分为多个可见 DOM 根的可编辑表格补失败回归测试，再让 `editable_table.fill_row` 消费已解析执行令牌，禁止按原始表名或 fieldid 二次选根

## 4. 收口与验证

- [x] 4.1 删除已被统一 module 替代的重复表格解析 helper 和 private helper 测试，保留最小 Playwright adapter 集成测试
- [x] 4.2 更新 `CONTEXT.md`、DSL 参考或用户文档以及报告字段说明，明确表格作用域、hard fieldid、歧义和诊断语义
- [x] 4.3 运行聚焦 pytest、至少一个安全真实 DSL、完整 `pytest`、`openspec validate centralize-table-scope-resolution --strict`、语言检查和 `git diff --check`
- [x] 4.4 重跑收入分成和管理费配置真实 DSL、相关聚焦 pytest、完整 `pytest`、严格 OpenSpec 校验、语言检查和 `git diff --check`
