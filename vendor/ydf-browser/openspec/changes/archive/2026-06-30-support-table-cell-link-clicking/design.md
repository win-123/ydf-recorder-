## Context

当前 DSL 已有三类相邻能力：`table_row_selection.select` 用于勾选业务行，`table_row_action.click` 用于 hover 后点击行级按钮，`table.capture_row_values` 用于按行和列读取单元格值。新的真实场景来自 `盘点任务填报` 未盘点页签：表格列 `任务编码` 的模板组件名是 `link`，`data_field=billCode`，用户要点击目标行该列内的任务编码链接。

这个入口不属于工具栏，也不是 hover 后出现的行级按钮。同页还存在顶部和行级 `查看任务` 按钮，如果用 `toolbar.click` 或扩大 `table_row_action.click` 语义，运行时容易点到错误动作。

## Goals / Non-Goals

**Goals:**

- 增加 `table.click_cell_link`，表达“在目标表格行的目标列中点击链接”。
- 复用已有表格作用域解析、行定位、列身份匹配和横向滚动能力。
- 点击后复用现有动态模板切换、通知捕获和错误提示处理。
- 为真实用例 `/Users/ken/temp/ydf-browser-问题反馈/实物管理-易耗品物资-盘点任务填报-未盘点页签查看任务-0001.yaml` 补上被注释的最后一步能力。

**Non-Goals:**

- 不新增全局 `link.click`；全页面裸链接点击会放大同名误点风险。
- 不把 `toolbar.click` 扩展为可点击表格文本。
- 不改变 `table_row_action.click` 的含义；它仍只表示行级动作按钮。
- 不在本 change 中支持不可编辑表单链接；后续可独立增加 `form.click_link`。

## Decisions

1. 新 DSL 使用 `component: table`、`operation: click_cell_link`。

   备选方案是 `table_row_action.click` 增加 `column`，但它已经以 `target.action` 为核心，语义是行级按钮。单元格链接的核心身份是列，放进 `table` 组件更清楚，也能复用 `table.capture_row_values` 的行列模型。

2. 目标字段采用 `target.column` 和可选 `target.link_text`。

   `target.column` 是必须字段，负责定位单元格；`target.link_text` 只在一个单元格有多个链接或需要校验具体编码时使用。不强制填写 `link_text`，因为真实业务里目标列通常只有一个链接，重复写编码会让 YAML 更脆。

3. 行定位复用现有表格规则。

   支持 `target.match`、`target.row_number`、`target.first_available` 和 `target.table`。这样树形表格展开、WUI header/body 分离、`table_fieldid` 推断和多表格歧义处理都沿用已有路径，不重新发明一套选择器。

4. 运行时只在目标单元格内找可点击链接。

   候选应优先包含 `a`、`button`、`[role=link]`、模板组件为 `link` 的单元格内可接收 pointer event 的元素。找不到时失败，不退回全页面文本点击。

5. 点击后走点击类动作后处理。

   executor 应像 `toolbar.click` 和 `table_row_action.click` 一样，在点击前启动通知捕获，点击后等待动态模板并尝试上下文切换。报告中记录 `column`、行定位、`table_fieldid` 和可用的 `row_search`。

## Risks / Trade-offs

- 目标单元格 DOM 可能不是标准 `a` 标签 -> 通过模板 `component_name=link` 和 pointer-event 可点击点兜底，但仍限定在目标单元格内。
- 多张表格同列同值时可能歧义 -> 继续依赖现有 `target.table` 和列归属推断，无法唯一确定时失败。
- 链接点击可能打开详情页、弹窗或仅触发通知 -> 复用现有动态模板和通知捕获路径，避免为链接单独做分支。
- 不支持表单链接会留下后续需求 -> 这是刻意缩小范围；表单链接没有行列定位，适合后续独立 `form.click_link`。
