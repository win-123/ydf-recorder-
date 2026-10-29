## Context

`editable_table.fill_row` 当前会按列身份激活目标单元格，然后根据模板组件名、运行时 DOM 和目标值选择普通文本、choice/dropdown 或 popup reference 录入路径。既有逻辑对 `YDFTreeModalSelect`、`YDFTableModalSelect`、`YDFReferSelect` 和部分运行时可见参照触发器已有覆盖。

本次问题出现在 `入库填报` 的 `物资入库` 子表：`物资分类` 模板列是普通 `YDFInput`，但真实交互会打开“选择物资类别”弹出参照，弹窗内是左树右表。DSL 已用结构化值表达业务意图：

```yaml
物资分类:
  tree:
    label: A05040101 复印纸
  first_available: true
```

运行时没有把该目标识别为参照语义，而是进入普通文本路径，把 Python dict 字符串写进单元格，导致弹窗残留并污染后续列录入。这个问题说明：可编辑表格列的参照判断不能只依赖模板组件名或 cell root 内是否已有触发器；目标值本身的结构化语义也是强信号。

## Goals / Non-Goals

**Goals:**

- 让 `editable_table.fill_row` 中包含弹出参照语义的结构化目标优先进入 popup reference 流程，即使模板列组件是 `YDFInput`。
- 结构化参照目标无法完成选择时，给出明确失败和诊断，不允许回退为普通文本写入。
- 支持当前真实用例中的左树右表参照：先应用 `tree` 上下文，再按 `first_available` 选择右侧候选并确认回填。
- 保持普通文本、数字、枚举下拉和既有参照列行为兼容。
- 在字段级结果中透传 `selected`、`popup_tree_context`、`confirmed`、`confirm_label` 等参照诊断，便于报告驱动排查。

**Non-Goals:**

- 不新增低层 DOM 点击 DSL，也不要求用例作者拆成“打开参照、点树、点行、确认”多步。
- 不把所有 `YDFInput` 都视为参照字段；只有目标值具有结构化参照语义或运行时确实检测到参照触发器时才走参照路径。
- 不改变页面级 `tree.select` 语义；这里的 `tree` 仍然只表示弹出参照内部上下文。
- 不在本变更中解决 `存放仓库` 标量树参照的 DSL 表达问题；该列仍应按既有 `YDFTreeModalSelect` 规则处理。

## Decisions

1. 以目标值结构作为可编辑表格参照分流的强信号。

   当 `editable_table.fill_row` 的字段值是包含 `tree`、`trees`、`tab`、`tabs`、`match`、`matches`、`row_number`、`row_numbers`、`first_available`、`select_first_available`、`selections`、`selection`、`values` 等参照目标键的对象时，运行时应视为结构化弹出参照目标。该判断应早于普通文本写入，也不能被 `YDFInput` 元数据覆盖。

   替代方案是继续依赖模板组件名和 cell DOM 中的触发器，但这正是本问题的失败点：真实字段在模板上是 `YDFInput`，触发器又不一定在 cell root 检测范围内。

2. 结构化参照目标只允许成功选择或明确失败，禁止降级文本录入。

   如果目标是结构化参照，`_select_popup_reference` 无法打开弹窗、无法选择候选或无法回填时，当前字段必须失败。错误信息要包含表格名、行号、列名、目标结构、列身份、当前可见弹窗或单元格诊断。实现不得进入 `_set_text_field_value(str(value))` 分支。

   替代方案是在 popup 失败后尝试普通文本兜底，但这会再次把 dict 写进业务单元格，属于错误成功。

3. 参照打开流程要支持“激活单元格后弹窗已出现”的形态。

   对结构化参照目标，激活单元格后应先检查当前是否已有新的可见 popup reference shell/choice root；如果已有，直接复用该弹窗执行树和候选选择。若没有，再按现有触发器查找和点击逻辑打开。这样兼容 `YDFInput` 激活后直接弹出参照的页面，也保留已有带显式图标的参照列。

4. `tree` 上下文执行顺序沿用既有 popup reference 语义。

   结构化目标进入 popup reference 后，执行顺序保持为：解析当前参照根 -> 应用 `tab` 上下文 -> 应用 `tree` 上下文 -> 执行过滤/候选匹配 -> 选择行或候选 -> 确认或等待回填。`tree` 不作为最终字段值；`first_available` 才表示在当前树上下文下选择第一条可用候选。

5. 诊断从“步骤失败后猜测”前移到字段级结果。

   成功录入结构化参照时，`editable_table.fill_row` 字段结果应像表单和查询参照一样透传 `selected`、`popup_tree_context`、`confirmed`、`confirm_label`。失败时要避免只暴露后续列失败，优先在真正的结构化参照字段处失败。

## Risks / Trade-offs

- [Risk] 过宽的结构化目标识别可能把普通对象型输入误判为参照。→ Mitigation: 只识别已存在于弹出参照 DSL 的目标键组合；普通业务对象如果没有这些键，不改变行为。
- [Risk] 某些字段使用 `first_available` 但实际是普通下拉。→ Mitigation: 可编辑表格中这类结构化值本身已经是参照/候选选择语义，失败时应明确报无法打开或选择参照，而不是写入对象字符串。
- [Risk] 激活单元格后页面上可能已有其他残留弹窗。→ Mitigation: 打开前记录可见弹窗计数或候选根标记，优先使用激活后新增或当前前景最高层的参照根，并限定后续树/表/确认操作在该根内。
- [Risk] 真实页面上 `tree` 点击后右表异步刷新较慢，`first_available` 可能读到旧空表。→ Mitigation: 选树后等待参照候选根稳定，沿用或增强已有 tree-table popup refresh wait 和诊断。
- [Risk] 这个修复会暴露 `存放仓库` 标量参照的独立问题。→ Mitigation: 本变更先修复 `物资分类` 被字符串化的根因；后续若 `存放仓库: 北京总仓` 需要结构化写法或运行时支持，应作为单独问题处理。
