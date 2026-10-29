## 1. DSL 和 executor

- [x] 1.1 在 `ydf_browser/dsl.py` 增加 `table.click_cell_link` schema、示例和校验，要求 `target.column` 加一种行定位方式。
- [x] 1.2 在 `ydf_browser/executor.py` 分发表格链接点击步骤，复用现有表格作用域解析、行定位字段解析和 `table_fieldid` 推断。
- [x] 1.3 将 `table.click_cell_link` 纳入点击类动作后处理，覆盖通知捕获、动态模板等待、模板切换和步骤结果数据。

## 2. Runtime 点击能力

- [x] 2.1 在 Playwright runtime 增加按表格作用域、行定位和列名定位目标单元格的链接点击方法。
- [x] 2.2 优先点击目标单元格内的 `a`、`button`、`[role=link]` 或模板 `link` 列对应的可接收 pointer event 元素，不退回全页面文本点击。
- [x] 2.3 支持 `target.link_text` 精确限定单元格内链接文本，并在无链接、链接文本不匹配或目标列不存在时给出明确错误。
- [x] 2.4 复用现有表格横向滚动和树形表格行搜索诊断，成功或失败时保留 `row_search`。

## 3. 测试和验证

- [x] 3.1 增加 DSL 校验测试，覆盖合法写法、缺少 `target.column`、缺少行定位属性。
- [x] 3.2 增加 executor 测试，确认步骤把 `column`、`link_text`、`table_fieldid` 和行定位传给 runtime，并记录动态模板和通知数据。
- [x] 3.3 增加 runtime 测试，覆盖 link 组件列、`link_text` 精确匹配、无链接失败和不退回全页面文本点击。
- [x] 3.4 将 `/Users/ken/temp/ydf-browser-问题反馈/实物管理-易耗品物资-盘点任务填报-未盘点页签查看任务-0001.yaml` 最后一步改为 `table.click_cell_link` 并真实跑通。
- [x] 3.5 更新用户文档和示例，说明 `table.click_cell_link` 写法、`target.column` / `target.link_text` 语义，以及它与 `toolbar.click`、`table_row_action.click` 的边界。
- [x] 3.6 运行 `openspec validate support-table-cell-link-clicking --strict`、`./scripts/check_openspec_language.py --change support-table-cell-link-clicking` 和完整 `./.venv/bin/python -m pytest`。
