## 1. 回归测试

- [x] 1.1 在 `tests/test_runtime.py` 增加失败测试：目标树子节点折叠、树外表格存在同名文本且页面其他区域存在输入框时，`tree.select` 不得点击树外文本，必须进入树内展开流程。
- [x] 1.2 补充并保持树组件自有搜索框优先、无搜索框回退展开、搜索未命中继续展开以及 checkbox/radio 优先选择的相关回归测试。

## 2. 运行时修复

- [x] 2.1 调整 `click_tree_node()` 的作用域传递，使用严格树根执行节点检查、文本匹配、展开和选择，仅将受限搜索作用域用于 `_try_search_tree_node()`。
- [x] 2.2 收紧树搜索框容器解析，使其只能使用目标树组件内可确认归属的输入框；无法确认时记录 `search_input_missing` 并复用既有展开流程。

## 3. 验证

- [x] 3.1 运行新增测试及现有树选择相关 runtime/executor 测试，确认严格树作用域、树搜索、多选和自动展开行为通过。
- [x] 3.2 使用仓库源码运行 `/Users/ken/temp/ydf-browser-问题反馈/功能-基础信息-账户管理-单位账户业务申请-提交-0001.yaml`，确认 `41 基本存款账户` 被真实选中，“开立”进入新增表单且报告不再包含 `请选择明细账户类别`。
- [x] 3.3 运行完整 `./.venv/bin/python -m pytest`，要求全部测试通过。
- [x] 3.4 运行 `openspec validate fix-tree-search-scope-false-positive --strict`、`./scripts/check_openspec_language.py --change fix-tree-search-scope-false-positive` 和 `git diff --check`。
