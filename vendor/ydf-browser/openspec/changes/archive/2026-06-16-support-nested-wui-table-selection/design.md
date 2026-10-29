## Context

真实用例 `/Users/ken/temp/ydf-browser-问题反馈/监督检查方案1.yaml` 在 `财会监督检查>>查前准备管理>>监督检查方案` 的检查分工页面失败。执行链路显示：

- `open_menu`、行级 `检查分工`、`添加小组`、小组组长参照、成员 `添加` 参照均能执行。
- 第 6 步后页面调试文本中已经出现内部检查小组成员行：`1 财会监督1 江西省 预算处 18766668888`。
- 原始第 7 步 `table_row_selection.select` 仍失败为未找到 `用户名称=财会监督1`。
- 将 DSL 临时改为 `table: 内部检查小组`、`column: 人员名称` 后仍失败。
- 将同一位置临时改为 `table.assert_column_values` 后，runtime 能解析到 `table_fieldid=2_2_tab` 和 headers，但列值采集为空；失败诊断同时显示页面 rows 中存在目标行。

当前实现中的关键约束：

- executor 已能把 `target.table=内部检查小组` 解析到子表 fieldid。
- runtime 的表格选择和数据值断言共用 `_table_selection_context()` 作为作用域入口。
- WUI 表格常见 `.wui-table-header` 与 `.wui-table-body` 分离渲染，`header.closest('.wui-table')` 不一定包含对应 body。
- 页面存在多张嵌套子表和重复列名，不能退回全页面裸文本匹配作为成功依据。

## Goals / Non-Goals

**Goals:**

- 在指定表格名称或 fieldid 后，runtime MUST 能解析同一业务表格的 header 与 body 关联容器。
- `table_row_selection.select` MUST 能在 `内部检查小组` 这类嵌套 WUI 子表中按目标列值定位并勾选数据行。
- `table.assert_column_values` 和 `table.assert_row_values` MUST 使用相同作用域能力读取该子表目标列。
- 失败诊断 MUST 能说明解析到的表格根、目标表头、候选行和选择器统计。
- 保持现有 DSL 语法兼容，不新增用户可见操作类型。

**Non-Goals:**

- 不新增 `toolbar.click target.table` 或改造工具栏动作定位语义；本 change 只修复表格作用域内的数据行选择和读取。
- 不把原始 DSL 的 `用户名称` 自动映射成 `人员名称`；用例应写页面真实列名。
- 不解决外部检查小组、被检查对象的业务数据准备问题，除非它们复用同一嵌套 WUI 表格机制。

## Decisions

1. 将修复集中在 runtime 表格作用域解析层。

   `table_row_selection.select`、`table.assert_column_values`、`table.assert_row_values` 已经共享 `table` / `table_fieldid` / `table_columns` 入口。把 header/body 关联修在 `_table_selection_context()` 及其 JS 解析脚本附近，可以同时覆盖行选择和断言，避免为每个 DSL 操作复制兜底逻辑。

   备选方案是只在 `select_table_row` 里加入全页面文本兜底。该方案会在多表格页面误选同名行，尤其当前页面同时存在内部检查小组、外部检查小组、被检查对象，不采用。

2. 表格 root 应表示“业务表格簇”，而不是只表示单个 header 或 body DOM 节点。

   对 fieldid 命中的 WUI 表格，解析逻辑应识别同一业务表格的 header/body 相邻容器或共同祖先，并优先返回一个能同时覆盖 header 与 body 的 root。若只能返回 header 或 body，后续列值脚本必须通过几何和 fieldid 线索找到配对容器，不能只在 `header.closest('.wui-table')` 内找行。

3. 列映射优先级保持 identity 优先、索引和几何兜底。

   对 header/body 分离表格，优先使用 `fieldid`、`data-fieldid`、`data-index`、`data-field`、`data-key` 等身份属性关联单元格。缺少身份时，才用同一表格簇中的列索引或 header 中心线几何对齐。这样可减少固定列副本、相邻列和嵌套表串列风险。

4. 原始反馈用例同步改成精确写法，但不以此替代程序修复。

   正确 DSL 应使用 `table: 内部检查小组` 和 `column: 人员名称`。不过诊断已证明即使这么写当前程序仍失败，因此用例修正是表达业务意图，程序修复仍是必要工作。

## Risks / Trade-offs

- [Risk] 扩大表格 root 到共同祖先后，可能包含兄弟子表。→ Mitigation: root 解析和列/行脚本都必须继续使用目标 fieldid、表名和表头集合过滤，只在同一业务表格簇内关联 header/body。
- [Risk] 固定列副本导致重复 header 和重复行。→ Mitigation: 保持 identity 优先，并在采集结果中去重；选择行时优先点击目标行内可见且可接收事件的 checkbox。
- [Risk] 真实页面数据随时间变化。→ Mitigation: 单元测试覆盖 DOM 结构；真实验证使用当前反馈 YAML，并保留报告路径作为证据。
- [Risk] 诊断过多影响可读性。→ Mitigation: 仅在失败路径附加 scoped debug，成功路径只保留必要 `table` / `table_fieldid` 数据。
