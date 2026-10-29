## 1. 回归测试

- [x] 1.1 在 `tests/test_runtime.py` 增加失败测试，证明复合条件换序不得改变树表展开范围，并且带前导数字的非树条件不得过滤真实父节点。
- [x] 1.2 增加目标表作用域测试，证明折叠节点枚举、行签名、目标重查和纵向滚动只使用已解析的 `table_fieldid` 对应表格，不触碰其它表格。
- [x] 1.3 在 `tests/test_executor.py` 增加成功步骤 `data.row_search` 和失败诊断回归，覆盖完整匹配条件及目标表格身份。

## 2. 树表行选择修复

- [x] 2.1 让 `_click_row_checkbox_by_match_values()` 将 `table`、`table_fieldid`、`table_columns` 传入现有树表展开 helper，并让目标行重查复用同一表格上下文。
- [x] 2.2 将折叠节点枚举、可见行签名和表格滚动限定到 `_table_selection_context()` 解析出的目标表格，每轮点击后重新查询当前 DOM。
- [x] 2.3 保留单值层级编码的安全前缀优化；复合条件禁用基于第一个条件值的祖先推断，统一按完整 AND 条件判断最终目标行。
- [x] 2.4 补充 `last_table_tree_search` 诊断字段，并在 `table_row_selection.select` 成功结果及失败错误中暴露目标表格、匹配条件、展开数、滚动数、命中状态和耗时。

## 3. 文档与验证

- [x] 3.1 更新 `AGENTS.md` 中树形表格规律，记录 `table_row_selection.select` 的目标表内展开、复合条件顺序无关和 `row_search` 诊断语义。
- [x] 3.2 运行新增测试和现有表格行选择、树表展开相关 runtime/executor 测试，确认普通表格、行级动作和单编码优化不退化。
- [x] 3.3 运行原始 `/Users/ken/temp/ydf-browser-问题反馈/流程-预算管理-调整调剂_财务-明细指标管理-分配正向-002.yaml`，确认第 3 步能展开并选择目标行；若目标数据已变化，保留遍历诊断并使用等价真实折叠行验证。
- [x] 3.4 运行完整 `./.venv/bin/python -m pytest`、`openspec validate fix-tree-table-row-selection-expansion-scope --strict`、`./scripts/check_openspec_language.py --change fix-tree-table-row-selection-expansion-scope` 和 `git diff --check`。
