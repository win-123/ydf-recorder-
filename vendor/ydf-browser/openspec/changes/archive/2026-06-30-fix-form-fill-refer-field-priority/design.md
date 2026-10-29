## Context

失败报告 `reports/20260630-191854-5ec9f679/report.json` 中，`editable_table.add_row target.editor=form` 已成功打开动态子表行表单，后续失败发生在第 5 步 `form.fill` 的 `采购品目`。

当前 manifest 中有两个同名字段：

- `采购预算信息 / YDFInput / bgtPurItemName / props.disabled=1`
- `采购内容及金额 / YDFTableModalSelect / purItemCode / dataType=refer`

运行时应选择第二个字段。实际 `_require_form_field("采购品目")` 先返回了 disabled 展示字段，导致 `fill_form_field()` 看到的 candidate 不再声明表格参照，最终进入普通 choice 路径并报 `无可见下拉/参照候选`。

## Goals

- 让 `form.fill` 在同名候选中优先使用可编辑参照字段。
- 保持既有前景字段优先、query/main table 排除和普通下拉行为不变。
- 用最小代码改动修正共享排序点，避免给单个业务字段写特例。

## Non-Goals

- 不新增 DSL 字段或 selector。
- 不改变 `editable_table.add_row editor=form` 的动态模板切换语义。
- 不处理第二个 case 的 `未找到默认组织: 101001`，那是独立上下文数据问题。

## Design

在 `_form_field_priority()` 或其调用点中补齐模板字段自身的可编辑性排序：

- `candidate.raw.props.disabled/readOnly/readonly` 或等价字段声明为只读时，应排在可编辑候选之后。
- `YDFTableModalSelect`、`YDFTreeModalSelect`、`YDFReferSelect`、`dataType=refer` 这类参照候选在 DSL 值是结构化参照目标时，应优先于同名普通展示字段。
- 仍保留 runtime 维度的前景、可编辑、控件身份排序，避免背景页或表格列被选中。

这样 `采购品目` 会先拿到 `purItemCode` 的 `YDFTableModalSelect` candidate，后续现有 `_candidate_component_claims_modal_reference()` 和 `_select_popup_reference()` 会继续负责打开参照、过滤 `A02010105`、按 `政府采购品目代码` 匹配并确认。

## Risks

- 某些历史用例可能依赖同名展示字段读取，但 `form.fill` 是录入语义，选择 disabled 展示字段本来不可写。若需要读取展示值，应使用断言或读取类能力而不是录入。
- 参照优先不应影响普通 `YDFSelect` 标量下拉。实现时仅在同名候选竞争且 DSL 值是结构化参照目标，或 candidate 明确不可编辑时改变排序。

## Verification

- 单测覆盖：同名 `采购品目` 候选中 disabled `YDFInput` 和可编辑 `YDFTableModalSelect` 同时存在时，`form.fill` 选择参照 candidate。
- 真实用例验证：重新运行 `/Users/ken/temp/ydf-browser-问题反馈/流程-预算执行-采购管理-采购计划新增审核-正向-0002.yaml`，确认第 5 步 `采购品目` 不再进入 choice-missing 失败。
- 收尾验证：`openspec validate fix-form-fill-refer-field-priority --strict`、语言检查、相关单测、最终全量 `pytest`。
