## Context

真实用例 `实物管理-易耗品物资-出库管理-已出库页签查询-0001.yaml` 在 `query.search` 录入 `单据类型=调拨` 时失败。页面实际打开的是 `.wui-select-dropdown`，候选包含 `分配`、`领用`、`报废报损`、`调拨`，字段模板为 `LCDEnum` 且带 `enumType=ammStockOutBillTypeEnums`。

当前 `fill_query_field()` 先判断弹出参照，再判断 choice/dropdown。`LCDEnum` 根节点里的下拉箭头会满足弹出参照触发器探测，导致普通枚举下拉被送入 `_select_popup_reference()`。

## Goals / Non-Goals

**Goals:**

- 让 `query.search` 中的 `LCDEnum` 或 `enumType` 查询字段按普通 choice/dropdown 选择候选。
- 如果页面下拉输入过滤后清空候选，或选择后字段未真实提交目标值，步骤必须失败，不能假成功。
- 保持 modal/reference 查询字段继续走弹出参照流程。
- 保持 `YDFTableModalSelect` 标量值必须使用结构化匹配目标的既有校验。

**Non-Goals:**

- 不新增 DSL 写法。
- 不修改弹出参照候选匹配、确认或恢复逻辑。
- 不扩大普通下拉候选选择器范围。

## Decisions

1. 在 `fill_query_field()` 内复用表单录入已有分流边界。

   若字段是 choice/dropdown，且模板组件或 raw 元数据不声明 modal/reference，则优先调用 `_select_query_choice()`。这比修改 `_root_has_popup_reference_trigger()` 更小，也避免影响真正弹出参照字段的触发器探测。

2. 保持 reference 优先级高于普通 choice。

   `YDFTreeModalSelect`、`YDFTableModalSelect`、组件名包含 refer/reference/modalselect，或 raw 中存在 `refuri` 的字段仍应进入弹出参照流程。`YDFTableModalSelect` 的标量校验继续由 `_ensure_table_reference_target_uses_match()` 兜住。

3. 普通查询 choice 使用无滚动打开路径。

   真实页面里 `LCDEnum` 的字段根点击只会让控件获得焦点，不一定展开候选层；运行时已有 `_open_choice_field_without_scroll()` 会在根内优先找 arrow/input 并派发点击事件。枚举查询 choice 分支应通过 `root_already_active=True` 复用这条路径，而不是新增另一套点击逻辑。

4. 枚举查询 choice 必须校验提交值。

   对 `LCDEnum` / `enumType` 查询字段调用 `_select_query_choice()` 时传入 `require_value_match=True`。如果页面自身在输入 `调拨` 后清空候选，或候选点击没有把字段值提交为 `调拨`，运行时必须报 choice/dropdown 错误，而不是继续点击查询按钮。

5. 只补一个聚焦单测和真实 YAML 验证。

   这个 bug 是查询字段分流顺序和成功判定问题，不需要新增跨模块抽象。单测覆盖 `fill_query_field + LCDEnum + arrow trigger`，真实验证覆盖页面端 `.wui-select-dropdown` 行为和未提交值时的失败诊断。

## Risks / Trade-offs

- [Risk] 普通 choice 优先可能误绕过真实弹出参照。→ Mitigation: 仅在 `_candidate_component_claims_modal_reference(candidate)` 为 false 时优先 choice；modal/reference 字段仍走原流程。
- [Risk] 真实页面的枚举下拉本身存在输入过滤缺陷。→ Mitigation: 不兼容该页面缺陷；如果无法提交目标值，步骤按 choice/dropdown 失败。
