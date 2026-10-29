## Context

`选择项目预算` 是一个前景弹窗主子表参照。弹窗上半区是 `项目预算` 主表，下半区是 `预算编制科目` 子表。手工或真实鼠标点击主表第 1 行 radio 后，主表行变成 `wui-table-row selected`，下方子表立即加载 `009 预算编制科目`、`jybz02 教育编制02` 等数据。

当前 `popup_reference.select target.selections[].row_number` 在同一页面失败，错误为 `未找到弹出参照第 1 行`。最大化/1920x1080 headed 验证仍失败，因此不是显示不全。probe 显示真实点击后行级 class 已经包含 `selected`，但行内 `input.checked` 仍为 `false`；runtime 现有 `_popup_reference_candidate_has_selection_state()` 在存在 selectable control 时主要看 input checked 或控件 wrapper checked，导致把已经选中的 WUI 行误判为未选中。

## Goals / Non-Goals

**Goals:**

- 修复弹出参照表格行选择后的选中态判定，让 WUI 行级 `selected` / `aria-selected` 也能作为有效选中证据。
- 保持 `popup_reference.select` 现有 DSL 不变，继续支持 `row_number`、`match`、`first_available` 和 `selections`。
- 确保判定限定在当前弹出参照表格行根内，不把背景页面、固定列副本或普通 hover/active 状态误当作参照选择成功。
- 增加单元回归和真实用例验证，覆盖 `选择项目预算` 主子表联动。

**Non-Goals:**

- 不新增 `popup_reference` DSL 字段。
- 不改变普通页面表格 `table_row_selection.select` 的语义。
- 不重新设计弹出参照根识别、确认按钮、查询条件或树上下文能力。
- 不把所有 `active/current` class 都全局视为业务选中，只在弹出参照候选行选择确认阶段使用。

## Decisions

1. 以“行根选中态”补充“控件选中态”。

   当候选位于表格行内，且行根或等效行根呈现 `selected`、`aria-selected=true`、`aria-checked=true` 或明确的 checked 状态时，runtime MUST 判定为已选中，即使该行内 `input.checked` 仍为 `false`。这是该 WUI 参照的真实行为：组件用行级 class 表示选择，隐藏/内部 input 不一定同步 checked。

   替代方案是继续强制 input checked，但这会重复点击或误判失败；也不能手工设置 `input.checked=true`，因为之前已经验证过那会制造假的选中状态而不触发业务联动。

2. 行根解析必须优先使用当前候选所属表格行。

   选中态判断应从候选节点向上找到最近的 `tr`、`[role=row]`、`.wui-table-row`、`.ant-table-row`、`.u-table-row` 或通用 table-row class。检测 selected 时优先检查这个 row，而不是只检查最内层 radio/input 节点。对于存在固定列和滚动主体副本的表格，点击目标和选中判断应对应同一行根。

3. row-number 点击成功后不应仅依赖控件 checked。

   `_click_popup_reference_table_row_by_index()` 点击目标、等待稳定后，应调用统一的选中态 helper。该 helper 要先看控件状态，再看行根状态；如果行根 selected 且弹窗内相关子表内容已刷新，也应视为成功。

4. 真实验证以原始问题用例为准。

   实现阶段必须至少跑 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-项目预算-YDF-81116-0001.yaml` 或等价最小 probe。验收信号不是只越过第一行点击，还要能处理 `selections` 中第二个 `预算编制科目` 表格选择，并点击弹窗 `确定` 完成参照选择。

## Risks / Trade-offs

- [Risk] 过宽的 `/selected|active|current/` class 判断可能把鼠标 hover 或焦点态误认为选中。-> Mitigation: 仅在弹出参照候选行选择路径启用，并优先限定到表格行根；对 `focused`、`hover` 这类状态不作为成功依据。
- [Risk] 固定列表格可能有左侧固定列行和主体行两个 DOM 副本，只有一个副本出现 selected。-> Mitigation: 在判断当前行根外，可按行文本或行索引寻找同一表格区域内的等效 selected 行，但仍限定在当前弹窗/表格根。
- [Risk] 有些参照点击行后不会勾选控件，只加载下方子表，最后仍需选择子表行才能确认。-> Mitigation: 对主子表场景，主表行 selected 即表示第一阶段选择成功；后续 `selections` 继续处理子表行。
- [Risk] 真实环境数据顺序可能变化，`row_number: 1` 选到的主表不同。-> Mitigation: 本 change 只修 row_number 选择机制；稳定业务用例可后续改用 `match` 约束具体项目预算。

## Migration Plan

- 向后兼容，无 DSL 迁移。
- 修复后旧用例仍按原 `popup_reference.select target.selections` 写法执行。
- 如果实现发现某些页面的 `selected` class 不是业务选择态，应通过更精确的行根/表格根限定和测试收紧，不回退到强制 input checked。
