## Context

`/Users/ken/temp/ydf-browser-问题反馈/监督检查方案3.yaml` 的第 7 步使用 `table_row_selection.select`，目标是 `内部检查小组` 表格中 `人员名称=财会监督1` 的成员行。失败报告显示 runtime 已解析到 `table_fieldid=2_2_tab`，表格根内有 1 行数据，文本包含目标成员，但 `selectableRows=0`，因此当前实现报 `未找到表格行选择框`。

当前代码已有 `_try_click_table_row_for_selection(row)`，但只在部分文本匹配路径使用。按列值匹配路径 `_click_row_checkbox_by_match_values()` 在目标行存在时只尝试 `_try_click_row_checkbox(row)`，失败后立即报错。

## Goals / Non-Goals

**Goals:**

- `table_row_selection.select` 在指定表格作用域内按列值命中目标业务行后，若没有 checkbox，可点击该业务行触发行高亮/选中。
- 有 checkbox 或等效控件时仍优先点击控件，保持既有选择语义。
- 失败诊断继续区分目标行不存在和目标行存在但无法选择。
- 用最小回归测试覆盖无 checkbox 行点击路径，并用真实反馈 YAML 验证。

**Non-Goals:**

- 不新增 DSL 字段或新组件。
- 不把 `table_row_selection.select` 变成任意表格单元格点击；点击单元格链接仍属于其它能力。
- 不退回全页面文本点击，避免多表格页面误选同名行。
- 不改变 `select_all` 的表头 checkbox 语义。

## Decisions

1. 复用已有 `_try_click_table_row_for_selection(row)`。

   原因：项目已有行点击兜底，行为边界清楚。只需在列匹配命中目标行但无 checkbox 时调用它，避免新增一套选择状态模型。

2. 控件优先，行点击兜底。

   有 checkbox 的表格仍优先点击 checkbox。只有 `_try_click_row_checkbox(row)` 返回失败时，才尝试点击目标行。这样不破坏需要真实勾选态的工具栏批量操作页面。

3. 只在已命中的业务行上点击。

   行定位仍由现有 `_find_visible_table_data_row_by_values()` 和 `_table_selection_context()` 完成。实现不增加全页面裸文本查找，也不修改表格作用域解析。

4. 测试先锁定 runtime 分支。

   这次缺口在 runtime 分支，不在 executor 分流。最小测试应模拟列匹配命中 row、checkbox 点击失败、行点击成功，并断言不会报错。

## Risks / Trade-offs

- [Risk] 某些表格点击行只聚焦、不形成业务选择态。→ Mitigation: 保留真实 YAML 验证；若后续页面需要可观测选中态，再补状态确认，不在本 change 里扩展。
- [Risk] 行内存在链接或按钮时点击整行可能触发其它动作。→ Mitigation: 只作为无 checkbox 兜底，并且只点击已匹配的目标行；有显式单元格链接点击需求继续使用专门能力。
- [Risk] 真实页面数据状态变化导致验收进入后续业务失败。→ Mitigation: 判断原问题是否消失以第 7 步越过为准；若后续业务数据失败，单独记录。
