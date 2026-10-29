## 1. 回归测试

- [x] 1.1 为普通树新增搜索优先单元测试：目标树区域内存在搜索输入框时，`click_tree_node` 先填入目标标签并触发搜索，再选择节点。
- [x] 1.2 为搜索失败回退新增单元测试：搜索框缺失、填值失败或搜索后无目标节点时，继续走现有展开遍历。
- [x] 1.3 为多选树新增幂等测试：搜索后优先点击 checkbox/radio，已选节点不被重复点击反选。

## 2. 运行时实现

- [x] 2.1 在普通树选择运行时中限定目标树区域，识别树内可见搜索输入框和搜索触发按钮。
- [x] 2.2 在 `click_tree_node` / `select_tree_node` 流程中加入搜索优先路径，搜索后重新查询当前 DOM 并复用现有节点选择逻辑。
- [x] 2.3 保留现有展开遍历作为兜底，并在失败诊断中记录搜索尝试和回退原因。

## 3. 验证

- [x] 3.1 运行新增和相关既有测试：`tests/test_runtime.py`、`tests/test_executor.py` 中的树选择用例。
- [x] 3.2 运行真实用例 `/Users/ken/temp/ydf-browser-问题反馈/business_object_create (2).yaml`，确认第 2 步 `tree.select label=流程管理` 成功越过。
- [x] 3.3 运行 `openspec validate support-tree-search-selection --strict` 和 `./scripts/check_openspec_language.py --change support-tree-search-selection`。
