## 1. DSL 校验

- [x] 1.1 在 `ydf_browser/dsl.py` 中新增 `TABLE_ASSERT_COLUMNS_EXAMPLE`，并把 `("table", "assert_columns")` 加入 `COMPONENT_TARGET_SCHEMAS` / `VALID_COMPONENT_OPERATIONS`。
- [x] 1.2 为 `table.assert_columns` 增加 target schema，允许 `table`、`name`、`table_name`、`present`、`absent`。
- [x] 1.3 增加 DSL 校验逻辑：`present` / `absent` 至少一个非空，且二者如果出现必须是非空字符串列表。
- [x] 1.4 补充 `tests/test_dsl.py`，覆盖只写 `absent`、只写 `present`、同时写二者、缺少断言目标、列表格式错误和未知 target 属性错误示例。

## 2. Executor 表格断言分流

- [x] 2.1 在 `WorkflowExecutor` 中新增 `table.assert_columns` 分支和 `_execute_table_assert_columns`。
- [x] 2.2 复用现有表格作用域解析，支持 `target.table` / `target.name` / `target.table_name`，并将 `table_fieldid`、`table_columns` 传给 runtime。
- [x] 2.3 单个可见主表格且未指定 `target.table` 时自动限定到唯一表格；多张可见主表格且未指定时在采集前失败。
- [x] 2.4 校验 `present` 和 `absent`：缺失必需列或发现不应存在列时抛出包含 `headers` 的明确错误；成功结果写入 `table`、`table_fieldid`、`headers`、`present`、`absent`。
- [x] 2.5 补充 `tests/test_executor.py`，覆盖成功不存在列断言、成功存在列断言、发现不应存在列失败、缺少必需列失败、多表格省略 `target.table` 失败和指定表格作用域传递。

## 3. Runtime 表头采集

- [x] 3.1 在 Playwright runtime 中新增 `collect_table_headers(table=None, table_fieldid=None, table_columns=None)`，内部复用 `_table_selection_context(...)`。
- [x] 3.2 增加表头采集脚本，覆盖表格根内 header、header/body 分离渲染、固定列和常见 `wui/ant/u/el` 表格表头结构。
- [x] 3.3 实现横向滚动采集，循环收集并去重所有可到达表头，避免只读取当前视口列。
- [x] 3.4 实现列名归一化：去除前置必填标识和多余空白，但保持精确匹配，不做包含匹配或括号形态兜底。
- [x] 3.5 表头采集为空时返回带表格作用域的诊断信息，并由 executor 转成明确失败。
- [x] 3.6 补充 `tests/test_runtime.py`，覆盖目标表格作用域、header/body 分离、横向滚动、必填星号归一化、前缀相似列名不互相匹配和空表头失败诊断。

## 4. 文档与用例

- [x] 4.1 更新 `AGENTS.md`，记录 `table.assert_columns` 的语义、`target.table` 规则、`present` / `absent` 写法和精确列名匹配限制。
- [x] 4.2 更新 `skills/gov-ydfdev-browser/references/dsl-reference.md`，补充 `table.assert_columns` 的 YAML 示例。
- [x] 4.3 更新 `docs/action-capability-test-plan.md`，加入表格列集合断言的验证点。
- [x] 4.4 整理 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-预算绩效-YDF-80424-0001.yaml` 中注释掉的旧式断言为 `table.assert_columns` 示例；如不改临时文件，则在 `examples/` 或 `tmp/` 增加等价验证样例。

## 5. 验证

- [x] 5.1 运行聚焦测试：`tests/test_dsl.py`、`tests/test_executor.py`、`tests/test_runtime.py` 中新增和相关用例。
- [x] 5.2 运行 `openspec validate support-table-column-assertions --strict`。
- [x] 5.3 如环境和账号可用，执行目标 YAML 验证 `预算绩效>>绩效模板>>模板库` 新增页中 `三级模板明细` 不存在 `一级绩效指标分值` 和 `二级绩效指标分值`。
