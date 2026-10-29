## 1. 回归测试

- [x] 1.1 新增真实 Playwright DOM 测试，证明空表新增打开表单时 runtime 返回未增行结构化结果且只点击一次，并先确认当前实现红灯。
- [x] 1.2 新增 executor 聚焦测试，覆盖未增行结果结合动态模板时成功、没有动态模板时失败。

## 2. 共享运行时修复

- [x] 2.1 调整可编辑表格新增浏览器脚本，在已点击候选后返回完整行状态和候选诊断，不再继续其它搜索上下文。
- [x] 2.2 调整 executor 未增行门禁，使空表和非空表在没有动态模板时都失败，并保留动态表单成功路径。

## 3. 规格与验证

- [x] 3.1 运行 `openspec validate fix-editable-table-form-add-row-completion --strict` 和语言检查。
- [x] 3.2 运行可编辑表格 runtime/executor 聚焦测试和相邻 DSL 测试。
- [x] 3.3 使用当前源码重跑原始真实 DSL，确认步骤 4 进入行编辑表单并继续执行后续步骤。
- [x] 3.4 运行完整 `./.venv/bin/python -m pytest -q`、`git diff --check` 并检查最终差异。
