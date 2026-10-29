## 1. DSL 与变量模型

- [x] 1.1 为 `table.capture_row_values` 注册 `COMPONENT_TARGET_SCHEMAS`，允许 `target.table`、`target.match`、`target.capture`，并补充错误示例。
- [x] 1.2 在 DSL 加载阶段预扫描 suite 内所有 `target.capture` 变量名，形成 runtime variable registry。
- [x] 1.3 扩展变量校验：允许 registry 中的占位符延迟运行期解析，继续拒绝未声明且不存在的变量。
- [x] 1.4 增加捕获变量名校验：禁止空变量名、非法来源列、`random` 命名空间和外部变量重名。

## 2. 运行期变量上下文

- [x] 2.1 新增 suite 级 `RuntimeVariableContext`，支持点号变量名 set/get、存在性检查和报告用快照。
- [x] 2.2 在 runner 创建 suite 执行上下文，并传入每个 case 的 executor。
- [x] 2.3 在 executor 步骤执行前解析运行期变量，变量未写入时在业务交互前失败。
- [x] 2.4 保持 `random.*` 的现有 executor 内解析和缓存行为，不被 suite 捕获变量覆盖。

## 3. 表格行值捕获执行

- [x] 3.1 实现 `_execute_table_capture_row_values` 或等价分发入口，解析 `target.table`、`target.match` 和 `target.capture`。
- [x] 3.2 复用现有表格作用域解析与 `collect_table_row_values()`，按匹配行读取所有来源列。
- [x] 3.3 捕获值为空、来源列缺失或匹配行不存在时整体失败，且不写入部分变量。
- [x] 3.4 捕获成功后一次性写入 suite runtime context，并返回 `captured`、`capture_sources`、`match`、`table`、`table_fieldid`、`row_search` 等报告数据。

## 4. 运行编排调度

- [x] 4.1 标记包含捕获步骤或引用 capture registry 变量的 suite 为 runtime-variable suite。
- [x] 4.2 在 `--concurrency > 1` 时保证 runtime-variable suite 内 case 按 YAML 顺序串行执行。
- [x] 4.3 保持不同 suite 之间以及普通 suite 的现有并发行为。

## 5. 测试覆盖

- [x] 5.1 增加 `tests/test_dsl.py` 覆盖 `capture_row_values` 合法写法、缺失 capture、非法变量名、未声明变量、捕获变量延迟解析。
- [x] 5.2 增加 `tests/test_variables.py` 覆盖运行期占位符保留、外部变量冲突、点号变量 set/get 和字符串拼接解析。
- [x] 5.3 增加 `tests/test_executor.py` 覆盖捕获成功、空值失败、来源列缺失、后续步骤引用捕获变量、同 case 引用和跨 case 引用。
- [x] 5.4 增加 `tests/test_runner.py` 覆盖 runtime-variable suite 的串行调度和普通 suite 并发不受影响。
- [x] 5.5 必要时补充 `tests/test_runtime.py`，确认捕获复用表格行值采集能力，并保留树形表格 `row_search` 诊断。

## 6. 文档与示例

- [x] 6.1 更新 DSL 示例或帮助文本，展示推荐写法 `capture: 变量名: 页面列名`。
- [x] 6.2 增加一个跨 case 示例：新增保存后捕获项目代码，后续待提交/审核 case 使用 `{{yjxm.project_code}}` 查询和选择同一业务数据。
- [x] 6.3 在报告说明中补充 `captured` 和 `capture_sources` 字段含义。

## 7. 验证

- [x] 7.1 运行 `openspec validate add-suite-runtime-capture-variables --strict`。
- [x] 7.2 运行 `./scripts/check_openspec_language.py --change add-suite-runtime-capture-variables`。
- [x] 7.3 运行相关单测；实现完成前至少先让新增失败用例覆盖目标行为。
- [x] 7.4 完整实现后运行 `env PYTHONPATH=. ./.venv/bin/pytest -q`。
