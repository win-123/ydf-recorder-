## Context

`form.fill` 目前先根据模板候选和运行时根节点判断字段类型。真实用例中 `支付业务类型` 被带入 popup reference 打开流程后，点击字段实际打开的是 `.wui-select-dropdown` 普通候选面板，候选中已有 `1 普通业务`，但运行时继续等待新增弹出参照 dialog，最终报 `未打开弹出参照选择框`。

既有 `form-choice-field-entry` 规格已经规定普通 choice/dropdown 字段不得因下拉箭头误走弹出参照。本变更只补齐进入 popup reference 打开流程后的运行时兜底，不新增 DSL 语法。

## Goals / Non-Goals

**Goals:**

- 标量 `form.fill` 目标在点击后出现普通 choice/dropdown 面板时，复用现有普通下拉选择流程。
- 保持真正弹出参照和结构化参照目标的既有行为。
- 用一个最小回归测试锁定 `.wui-select-dropdown` 已可见但 popup reference dialog 缺失的路径。

**Non-Goals:**

- 不改变 DSL 字段名匹配规则。
- 不处理当前真实用例后续 `开户银行` / `收款人开户银行` 绑定差异。
- 不新增通用页面点击或字段特例。

## Decisions

1. 在 `_select_popup_reference()` 点击触发器后检查普通下拉面板。

   理由：这是所有误入 popup reference 打开流程的共享入口，比在 `支付业务类型`、组件名或单个模板上打补丁更小。只有在目标值是标量、已有普通下拉面板可见、且没有新增弹出参照 dialog 时，才回退到 `_select_query_choice()`。

2. 复用 `_select_query_choice(root, fill_locator, value, root_already_active=True)`。

   理由：普通下拉候选查找、树形下拉展开、候选诊断和键盘提交已经集中在该流程中。本变更不新增一套候选点击逻辑。

3. 保留 `_resolve_popup_reference_dialog()` 失败后的兜底检查。

   理由：真实页面可能在短时间内打开面板或更新 DOM。前置检查覆盖快路径，异常兜底覆盖延迟出现的普通下拉面板。

## Risks / Trade-offs

- [Risk] 真正弹出参照页面中也存在下拉面板，可能被误判为普通 choice。→ Mitigation：只有未发现新增 dialog 时才前置 fallback；结构化目标仍不走 fallback。
- [Risk] 真实 DSL 仍可能失败在后续字段。→ Mitigation：交付说明单独报告后续 `开户银行` 绑定问题，不把它纳入本 change。
