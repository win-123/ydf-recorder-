## 1. DSL 校验

- [x] 1.1 在 `ydf_browser/dsl.py` 的 `table_row_selection.select` target schema 中允许 `select_all`。
- [x] 1.2 更新 `table_row_selection.select` 校验逻辑，允许 `target.select_all: true` 作为独立定位方式。
- [x] 1.3 增加互斥校验，禁止 `select_all` 与 `match`、`rows`、`row_number`、`row_numbers`、`row_index`、`first_available`、`select_first_available` 混用。
- [x] 1.4 补充 DSL 单元测试，覆盖接受 `select_all: true` 和拒绝混合行定位字段。

## 2. Executor 分流

- [x] 2.1 在 `WorkflowExecutor._execute_table_row_selection_select` 中解析 `target.select_all`，并在行号、行条件选择前分流。
- [x] 2.2 复用现有表格作用域解析，把 `target.table`、`table_fieldid`、`table_columns` 传递给 runtime 全选方法。
- [x] 2.3 复用多表格歧义检测，确保多张可见主表格且未指定 `target.table` 时失败，不执行 checkbox 点击。
- [x] 2.4 补充 executor 单元测试，覆盖单表全选、指定表格全选、多表格未指定表格失败和 runtime 失败原因透传。

## 3. Runtime 表头全选

- [x] 3.1 在 Playwright runtime 增加 `select_all_table_rows(...)`，复用 `_table_selection_context(...)` 限定表格根。
- [x] 3.2 实现表头 checkbox 候选定位，优先查找 `thead` / header 区内的原生 checkbox、`role=checkbox` 和常见 checkbox wrapper。
- [x] 3.3 实现 checked / mixed / unchecked 状态判断，已全选时直接成功，未选中或半选时点击可接收 pointer event 的表头 checkbox 或 wrapper。
- [x] 3.4 缺少可见表头 checkbox 时抛出明确错误，并包含表格作用域诊断信息。
- [x] 3.5 补充 runtime 单元测试，覆盖只点表头不点数据行、已选中幂等、半选/未选中点击、无表头 checkbox 失败、指定表格作用域。

## 4. 文档与示例

- [x] 4.1 更新 `AGENTS.md` 的 `table_row_selection.select` 语义说明，记录 `target.select_all` 和多表格 `target.table` 规则。
- [x] 4.2 更新 `skills/gov-ydfdev-browser/references/dsl-reference.md`，补充全选 YAML 写法。
- [x] 4.3 更新 `docs/action-capability-test-plan.md`，加入表头全选验证点。
- [x] 4.4 将 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-预算编制-YDF-80457-0001.yaml` 中临时 `row_number: 1` 写法整理为 `select_all: true` 的示例或临时验证用例。

## 5. 验证

- [x] 5.1 运行聚焦测试：`tests/test_dsl.py`、`tests/test_executor.py`、`tests/test_runtime.py` 中新增和相关用例。
- [x] 5.2 运行 `openspec validate support-table-select-all --strict`。
- [x] 5.3 如环境可用，使用该预算编制用例验证 `选择会计科目` 弹窗中 `select_all: true` 能成功勾选全部并继续点击 `确认`。
