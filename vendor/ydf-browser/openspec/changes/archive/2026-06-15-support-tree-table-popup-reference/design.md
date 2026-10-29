## Context

`一上支出预算编制` 的新增页中，`项目负责人` 字段在模板元数据里是 `YDFReferSelect`，`dataType=refer`，真实引用为人员信息参照。运行时点击字段右侧参照图标后会打开一个前景弹窗：左侧是部门/范围树，右侧是查询区和人员表格，表格行前有单选控件，底部按钮是 `保存/取消`。

现有运行时已经能点击字段并触发弹窗，但弹窗识别和确认逻辑偏向 `确定/确认`，导致 `保存/取消` 结构被判定为“未打开弹出参照选择框”。同时，当前 `popup_reference.select` 和结构化表单参照目标已有 `value`、`values`、`match`、`matches`、`row_number`、`row_numbers`、`first_available`、`selections`，但缺少“先在参照弹窗内选择左树，再在右侧表格匹配人员”的上下文表达。

这个问题不是普通下拉，也不是页面左侧 `tree.select`，而是表单字段内部参照弹窗自己的树表组合。设计需要保持 DSL 语义化，避免让用例作者写裸 DOM 选择器或低层点击步骤。

## Goals / Non-Goals

**Goals:**

- 在 `form.fill` 字段值中支持树表参照的结构化写法，表达参照内左树上下文、右侧表格匹配、确认保存和字段回填。
- 让 `YDFReferSelect` / `dataType=refer` 的结构化目标走弹出参照路径，避免被普通 choice/dropdown 逻辑误处理。
- 让弹出参照识别支持底部为 `保存/取消` 的弹窗，并把 `保存` 纳入默认确认按钮。
- 让同一目标结构可复用于 standalone `popup_reference.select`，减少两套 DSL 语义分叉。
- 保持已有普通下拉、树下拉、`YDFTableModalSelect`、`YDFTreeModalSelect`、表格参照和旧 `popup_reference.select` 写法兼容。

**Non-Goals:**

- 不设计通用任意弹窗自动化 DSL；本变更只覆盖弹出参照选择。
- 不改变页面级 `tree.select` 的语义，也不把参照内树选择暴露成独立页面步骤。
- 不要求一次实现任意复杂多树联动；第一阶段支持参照弹窗内一个上下文树目标，保留 `trees` 扩展入口。
- 不调整登录、菜单打开、模板匹配或页面级表格树展开能力。

## Decisions

1. 使用 `tree` 作为参照内上下文，而不是新增 `popup_tree.select` 步骤。

   DSL 示例：

   ```yaml
   项目负责人:
     tree:
       label: 101 综合司01
     match:
       column: 人员名称
       equals: 人员二十一
   ```

   这种写法把“选择项目负责人”保持为一个字段录入动作。替代方案是新增独立步骤，例如先打开字段、再选弹窗树、再选表格行、再保存；这种方案会把一个业务字段拆成多步低层交互，且容易和页面级 `tree.select` 混淆。

2. `tree` 接受字符串简写和对象写法，语义复用现有树目标字段。

   字符串简写等价于 `label` 精确匹配；对象写法支持 `label`、`value`、`node`、`name` 等和 `tree.select` 接近的目标描述，但作用域被限定在当前参照弹窗根内。运行时不得退回全页面裸文本点击。

3. 参照选择流水线固定为“打开字段 -> 识别弹窗 -> 选参照内树 -> 查询/匹配右表 -> 选行 -> 确认 -> 等待回填”。

   `tree` 只是上下文选择，不代表最终字段值；最终选择仍来自 `match`、`matches`、`row_number`、`row_numbers`、`first_available` 或 `selections` 中的表格候选。这样可以避免左树点击成功但人员没有被选择时误报通过。

4. `保存` 作为弹出参照默认确认按钮之一。

   现有逻辑优先找 `确定/确认` 合理，但人员参照底部真实按钮是 `保存/取消`。运行时应按 `确定`、`确认`、`保存` 的确认语义查找，也允许 `confirm_label` 显式覆盖。弹窗根识别也不能只依赖 `确定/确认`，应接受含标题、可选择候选区和 `保存/取消` 页脚的结构。

5. `YDFReferSelect` / `dataType=refer` 的结构化目标优先走弹出参照路径。

   当字段元数据或运行时 DOM 表明字段是 refer 控件，并且目标值是包含 `tree`、`match`、`matches`、`row_number`、`row_numbers`、`first_available`、`selections` 之一的对象时，运行时必须进入弹出参照选择流程。普通标量值仍保留现有 choice/dropdown 行为，避免破坏普通下拉字段。

6. standalone `popup_reference.select` 复用相同目标结构。

   已打开或由执行器打开的弹出参照，都应理解同一套 `tree`、`match`、`first_available`、`selections` 结构。实现上可以复用底层 helper，避免 `form.fill` 和 `popup_reference.select` 出现不同匹配规则。

## Risks / Trade-offs

- [Risk] 不同业务参照的按钮文案和弹窗 DOM 差异较大，过宽识别可能误把普通业务弹窗当参照。→ Mitigation: 根识别需要同时满足前景弹窗、候选列表/表格/树结构、取消按钮和确认按钮候选，不只按按钮文本判断。
- [Risk] 参照内左树和页面左树同名，裸文本点击会误点背景页面。→ Mitigation: 所有树查找、查询、行匹配和确认按钮都必须限定在当前可见前景弹窗根内。
- [Risk] `tree` 点击后右表异步刷新，立即匹配会读到旧表格。→ Mitigation: 选树后等待弹窗内表格候选稳定，必要时记录刷新前后行文本或加载状态。
- [Risk] `保存` 在部分编辑弹窗中也存在，新增默认确认可能扩大误点范围。→ Mitigation: 只有当前流程已经识别为弹出参照并完成候选行选择后，才使用参照确认按钮；普通 `toolbar.click 保存` 不复用这个逻辑。
- [Risk] `trees` 多上下文能力过早泛化会增加 DSL 复杂度。→ Mitigation: 第一阶段只要求 `tree` 单上下文稳定落地；`trees` 可先做校验保留或只按顺序处理明确数组，测试覆盖单上下文核心链路。

## Migration Plan

- 这是向后兼容扩展；已有 DSL 不需要迁移。
- 新 DSL 文档增加树表参照示例，说明 `tree` 只表示参照内上下文，最终值仍由 `match` 或 `first_available` 选择。
- 若实现发现某些旧用例显式依赖 `保存` 不被当作参照确认，应通过参照根识别收紧条件，而不是移除 `保存` 默认确认。

## Open Questions

- `trees` 是否在首个实现中完整支持多树顺序选择，还是仅在 schema 中保留并在运行时报“暂不支持多上下文树”，需要实现阶段根据真实 DOM 复杂度决定。
- `filter.conditions` 和右表 `match` 同时存在时，是否必须点击查询按钮，还是先尝试当前自动过滤结果；实现阶段应沿用已有参照策略：先尝试当前候选，找不到再提交过滤。
