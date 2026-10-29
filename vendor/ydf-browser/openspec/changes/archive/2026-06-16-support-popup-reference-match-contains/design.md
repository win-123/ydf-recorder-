## Context

`popup_reference.select` 和表单结构化参照目标已经共享 `_select_popup_reference()` 这一条运行时路径。DSL 校验器中的 `_validate_row_match()` 允许 `match` 使用 `equals` 或 `contains`，但运行时 `_click_popup_reference_table_row()` 只从 `match.equals/value/text` 读取目标值；诊断函数 `_collect_popup_reference_table_match_debug()` 也只报告这些字段。因此 `contains` 目标会在执行阶段变成空字符串。

真实复现链路是 `监督检查方案1.yaml`：前 5 步通过，`popup_reference.select` 打开的“添加”弹窗中已有 `财会监督1`，但 `match.contains: 财会` 失败并报告 `wantedValue: ""`。这说明菜单、登录、组织、过滤和基础数据都不是根因，缺口集中在弹出参照表格行匹配语义。

## Goals / Non-Goals

**Goals:**

- 让弹出参照表格行匹配正式支持 `match.contains`，覆盖 standalone `popup_reference.select`、表单字段结构化参照、`matches` 和 `selections`。
- 让匹配、诊断和错误信息读取同一份目标解析结果，避免 `contains` 执行失败时诊断显示空目标。
- 保持 `match.equals` 兼容；既有精确值用例和宽松包含匹配行为不应退化。
- 用单元测试覆盖运行时 helper，用真实 YAML 验证 `监督检查方案1.yaml` 至少能越过当前失败点。

**Non-Goals:**

- 不改变 `filter.conditions[].equals` 语义；过滤条件仍按当前字段和值写法提交。
- 不引入新的 DSL 字段名，也不改变 `table_row_action`、`table_row_selection` 或普通表格断言组件。
- 不扩展为正则、大小写折叠、拼音或多条件 contains；本次只补齐已经被 DSL 接受的单字段 `contains`。

## Decisions

1. 在运行时抽取或统一使用“行匹配目标解析”逻辑。

   `_click_popup_reference_table_row()`、`_collect_popup_reference_table_match_debug()` 和可能复用的表格选择路径应从同一规则读取目标值：优先 `equals/value/text/label`，其次 `contains`。同时保留匹配模式信息，让 `contains` 明确表示包含匹配，`equals` 保持既有兼容行为。

   备选方案是让 DSL 把 `contains` 归一化成 `equals`。这会掩盖语义差异，也会让报告无法区分作者期望的精确值还是包含值，因此不采用。

2. `contains` 只作用于目标列或目标行文本，不改变候选根解析和选择控件点击策略。

   当前真实失败发生在候选表格已经可见之后，因此不需要改弹窗识别、过滤提交、确认按钮或选择态稳定逻辑。实现应把变化限定在“哪些行算匹配”这一层。

3. 诊断必须跟随新语义。

   如果 `contains` 匹配失败，`row_debug.wantedValue` 必须显示 `contains` 的值，`rows` 采样也应按该值筛选。这样后续真实失败能区分“页面确实没有包含值的候选”与“运行时没有读到目标值”。

## Risks / Trade-offs

- [Risk] 既有 `equals` 目前实际允许 `cellText.includes(wanted)`，实现 `contains` 时如果顺手收紧 `equals` 可能破坏旧用例。→ Mitigation: 本 change 不收紧 `equals`，只让 `contains` 不再为空；如果未来要收紧精确匹配，应另开 change。
- [Risk] 多列同名或重复 header 下，短 `contains` 可能匹配到非预期行。→ Mitigation: 仍优先使用 `match.column` 限定列；建议真实用例在可稳定时使用更具体的 `equals`。
- [Risk] 真实页面弹窗中同一 `contains` 命中多行时，当前运行时会选择第一条可点击候选。→ Mitigation: 保持现有单目标匹配习惯；如业务需要多行消歧，使用更精确的 `equals`、`row_number` 或后续新增多条件能力。

