## 1. 复现与测试

- [x] 1.1 保留当前失败证据：原始 YAML 第 4 步 `target.table=dzkxxx_table + first_available=true` 失败，报告路径记录为 `/tmp/ydf-income-recpay-pub-report.json`。
- [x] 1.2 在 `tests/test_executor.py` 或现有 fixture 测试中补充 `table_row_selection.select target.first_available` 指定表格时应向 runtime 传递表格作用域和第 1 行选择意图的回归测试。
- [x] 1.3 在 `tests/test_runtime.py` 补充 runtime 测试：目标表第一条有效业务行没有 checkbox 时，`first_available` 行号选择应点击该业务行。
- [x] 1.4 补充 runtime 测试：第一条有效业务行存在 checkbox 时仍优先点击 checkbox，不退化为点击整行。
- [x] 1.5 补充 runtime 测试：`暂无数据`、小计/合计行和表头不应被当作 first available 候选。

## 2. 实现

- [x] 2.1 梳理 `WorkflowExecutor._execute_table_row_selection_select()` 到 `PlaywrightRuntime.select_table_row_by_index()` 的调用链，确认 `first_available` 的表格作用域传递路径。
- [x] 2.2 在行号选择实现中复用已有有效业务行判断和 `_try_click_table_row_for_selection()`，当目标行无 checkbox 或等效选择控件时，在目标表格作用域内点击该业务行。
- [x] 2.3 保持有 checkbox 行的既有点击路径优先，并保持多表格歧义检测、`target.table` 解析和 `table_fieldid` 结果不退化。
- [x] 2.4 改善失败信息：无有效业务行、表格作用域解析失败、目标行无可操作节点时，错误中保留目标表格、行号、表格根摘要和选择器统计。

## 3. 文档与样例

- [x] 3.1 更新用户可见 DSL 文档或示例，说明 `table_row_selection.select target.first_available` 表示目标表格第一条有效业务行，表格有 checkbox 时点击 checkbox，无 checkbox 时点击业务行。
- [x] 3.2 更新 `AGENTS.md` 中表格行选择规律，记录 `first_available` 不应隐含必须有 checkbox。

## 4. 验证

- [x] 4.1 运行相关单测：`./.venv/bin/python -m pytest tests/test_runtime.py tests/test_executor.py -k "first_available or table_row_selection"`。
- [x] 4.2 使用原始 YAML 的截断流程验证到 `zdbm_btn_modal_ok`：`dzkxxx_table first_available` 后选择 `second_table row_number=2`，确认生成 `发布明细`，但不执行最终 `保存`。
- [x] 4.3 未执行完整正向保存流程；当前验证按要求截断到 `zdbm_btn_modal_ok`，避免提交业务数据。
- [x] 4.4 运行 OpenSpec 门禁：`openspec validate support-table-first-available-row-click --strict` 和 `./scripts/check_openspec_language.py --change support-table-first-available-row-click`。
- [x] 4.5 运行全量测试：`./.venv/bin/python -m pytest`。
