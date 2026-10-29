## Context

`query.search` 目前的查询字段录入路径比 `form.fill` 窄。执行器从 `target.conditions[]` 取出 `equals` 后立即转成字符串，再调用运行时 `fill_query_field()`；运行时只区分“非 choice 文本填入”和“choice/dropdown 选择”。由于 `_looks_like_choice_field()` 会把包含 `select`、`tree` 的组件识别成 choice，`YDFTreeModalSelect` 这类弹出参照会被误送到普通下拉选择逻辑。

`form.fill` 已经有更完整的字段分流：先排除 modal/reference 控件的普通 choice 路径，再对 `YDFReferSelect`、`YDFTreeModalSelect`、`YDFTableModalSelect` 或 refer 元数据走 `_select_popup_reference()`。本变更将查询字段补齐到同一类判断，但查询组件仍保留自身“填写条件并点击真实查询按钮”的语义。

## Goals / Non-Goals

**Goals:**

- 查询条件字段为 `YDFTreeModalSelect`、`YDFTableModalSelect`、`YDFReferSelect` 或 refer/modal 元数据时，使用弹出参照选择流程。
- 支持查询条件 `equals` 传入标量、列表或结构化参照 target，避免执行器提前字符串化导致多选或结构化信息丢失。
- 普通文本框、普通下拉、`YDFTreeSelect` 查询条件继续沿用现有填值/下拉树逻辑。
- 步骤报告记录参照选择诊断，便于判断弹出参照是否确认、是否应用弹窗内树上下文、选择了哪些候选。
- 覆盖 `项目目录 = 101 财政一级` 和多选项目目录查询条件的回归测试。

**Non-Goals:**

- 不新增独立的 `query.popup_reference` DSL 组件。
- 不改变 `form.fill`、`popup_reference.select`、可编辑表格参照或页面左树 `tree.select` 的语义。
- 不为任意查询弹窗设计低层 DOM 操作 DSL；查询条件仍通过字段名和语义化目标表达。
- 不要求本变更一次覆盖所有业务参照弹窗差异；优先复用已有弹出参照选择能力。

## Decisions

1. `query.search` 继续使用现有 DSL 形态，扩展 `equals` 的运行时值语义。

   当前 YAML 已使用：

   ```yaml
   conditions:
     - field: 项目目录
       equals: "101 财政一级"
   ```

   这个写法应直接工作。多选查询条件可自然写成列表：

   ```yaml
   conditions:
     - field: 项目目录
       equals:
         - "101 财政一级"
         - "767 财务一级测试"
   ```

   结构化参照目标也保留在 `equals` 下，复用 `_normalize_popup_reference_target()` 支持的 `value`、`values`、`match`、`matches`、`row_number`、`first_available`、`selections`、`tree` 等语义。这样避免引入第二套查询专用参照 DSL。

2. 执行器不得提前字符串化 `condition["equals"]`。

   `value = str(condition["equals"])` 会破坏列表和结构化目标，也会让运行时无法区分用户真实输入与 JSON/字典文本。执行器应保留原值传给 `fill_query_field()`；仅在报告展示或 fallback 文本填入时再转换。

3. 查询字段分流使用与表单字段一致的 modal/reference 优先级，但不完整复制表单前景层解析。

   查询条件通常位于当前列表页查询区，不涉及表单弹窗中的前景层覆盖。因此 `fill_query_field()` 可以在解析 root 和 fill locator 后，按以下顺序处理：

   ```text
   modal/reference query field -> _select_popup_reference()
   plain text query field      -> fill
   normal choice/tree select   -> _select_query_choice()
   ```

   关键点是普通 choice 不能抢先吞掉 `YDFTreeModalSelect`。可复用 `_candidate_component_claims_modal_reference()` 和 `_looks_like_popup_reference_field()` 这类现有 helper。

4. `YDFTableModalSelect` 查询条件应沿用表格参照目标约束。

   已有表单和可编辑表格逻辑要求表格型参照使用 `match` 这类结构化目标，避免按标量误点错误行。查询字段如果是 `YDFTableModalSelect`，也应调用 `_ensure_table_reference_target_uses_match()`，保持跨组件一致。

5. 步骤结果保留原始可读值并附加参照诊断。

   普通查询条件报告仍包含 `field`、`equals`。当运行时设置 `last_popup_reference_result` 时，执行器把 `selected`、`confirmed`、`confirm_label`、`popup_tree_context` 合并到该条件结果中。列表或结构化 `equals` 在报告中保留为结构值，避免变成不可读字符串。

## Risks / Trade-offs

- [Risk] 过宽的参照判断可能把普通 `YDFTreeSelect` 查询条件误走弹出参照。→ Mitigation: modal/reference 分流只对组件名或元数据声明 `refer/ref/modalselect` 的字段生效；普通 `YDFTreeSelect` 仍走 `_select_query_choice()`。
- [Risk] 部分查询参照选择后不会立即回填到输入框，而是以 tag 或隐藏值形式呈现。→ Mitigation: 复用已有 `_select_popup_reference()` 的回填等待与诊断截图；如真实页面差异暴露，再在弹出参照底层能力中收紧。
- [Risk] 多选参照在选择过程中可能自动回填并关闭，导致剩余目标无法选择。→ Mitigation: 已有 `_select_popup_reference()` 对多目标提前关闭有明确错误，本变更不吞错。
- [Risk] `equals` 支持对象后，报告和 DSL 文档容易让用户误以为所有查询字段都支持结构化值。→ Mitigation: 文档明确结构化值只在查询字段是弹出参照时生效；普通下拉仍写可见选项文本。

## Migration Plan

- 这是向后兼容扩展；已有 `query.search` 文本、普通下拉和树形下拉用例不需要迁移。
- 当前失败用例可以继续保持 `equals: "101 财政一级"`。
- 如需要验证“项目目录可多选”，新增或调整用例为 `equals` 列表，而不是多个同名条件或低层点击步骤。
