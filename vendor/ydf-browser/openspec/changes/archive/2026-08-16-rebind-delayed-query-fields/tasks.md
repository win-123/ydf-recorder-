## 1. 查询字段重新绑定

- [x] 1.1 在 `tests/test_executor.py` 增加“页签绑定快照后查询输入才出现”的回归测试，并运行该单测确认以“未绑定查询字段”失败。
- [x] 1.2 在 `ydf_browser/executor.py` 对 manifest 已声明的缺失查询字段限时刷新当前 binding，保持编辑表单防误绑分支不变。
- [x] 1.3 运行新增回归测试及查询 runtime-only、编辑表单防误绑、页签重绑定相邻测试，确认全部通过。

## 2. 真实用例与交付验证

- [x] 2.1 使用当前源码运行“专家库-创建保存”真实 DSL，确认保存后无需再次 `open_menu` 即可按“专家姓名”查询并通过表格断言。
- [x] 2.2 运行完整 pytest、`openspec validate rebind-delayed-query-fields --strict`、语言检查和 `git diff --check`，核对 change 任务与实际结果一致。
