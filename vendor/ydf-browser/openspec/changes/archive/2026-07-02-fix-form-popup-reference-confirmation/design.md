## Context

当前 `form.fill` 会通过 `runtime.last_popup_reference_result` 报告弹出参照字段选择结果。真实用例 `/Users/ken/temp/ydf-browser-问题反馈/流程-预算管理-项目库-二级项目管理财务-新增-0001.yaml` 已复现：`项目联系人`、`项目负责人` 两个 `YDFReferSelect` 人员参照字段记录了 `selected`，但 `confirmed=false`，整体步骤仍然 `success=true`。

近期 `fix-popup-reference-tree-context-unique-candidate` 为了解决可编辑表格树形候选点击后已回填但选中态不可读的问题，增加了候选点击后的早退路径。该思路对有外层单元格回填校验的可编辑表格是合理的，但普通表单字段没有额外外层校验，不能把 `confirmed=false` 当作成功。

## Goals / Non-Goals

**Goals:**

- 让普通 `form.fill` 弹出参照字段只有在确认完成、字段真实回填或候选层真实关闭可证明时才成功。
- 保留可编辑表格参照的性能修复，避免恢复长时间 fallback 等待。
- 在报告中明确区分 `selected`、`confirmed`、字段回填和候选层关闭状态。
- 用真实人员参照 YAML 证明修复后的成功条件。

**Non-Goals:**

- 不新增 DSL 字段。
- 不改变 `filter.conditions + match` 的写法。
- 不重写所有弹出参照候选识别逻辑。
- 不放宽真实多候选自动选择规则。

## Decisions

1. 在普通表单字段成功边界修复，而不是改 YAML。

   这次 YAML 已经提供了 `filter.conditions` 和 `match`，运行时也记录了 `selected`。问题发生在运行时完成条件，所以修复点应在 `_select_popup_reference()` 和 executor 的 `form.fill` 字段结果判定。

2. 普通表单参照不接受无确认早退。

   对普通表单字段，`last_popup_reference_result.confirmed=false` 表示参照没有通过确认动作或等价关闭校验完成。executor 不应把它作为成功字段继续追加到 `filled`，而应让当前字段失败并暴露诊断。

3. 可编辑表格回填兜底保留在可编辑表格路径。

   可编辑表格单元格后续有 `_wait_for_editable_table_cell_backfill()` 这类外层校验。普通表单字段没有这个外层保障，因此不能复用同样的早退成功语义。实现时应通过调用路径参数或结果状态区分两者。

4. 弹层隐藏判断不能只依赖“选择面 + 确认按钮”组合。

   `PM_SELECT_MANAGER` 人员参照可能在 iframe 或前景层中暴露候选表格、保存/取消页脚和人员文本。隐藏判断应优先证明前景参照真的不可见；不能因为当前扫描没有同时命中候选面和按钮，就默认隐藏。

5. 报告保留早退原因。

   `confirmed=false` 的结果需要包含 `close_action`、`root_backfilled`、`dialog_hidden` 或等价诊断，便于后续判断是候选点击失败、弹层误判隐藏、确认按钮缺失还是字段未回填。

## Risks / Trade-offs

- [Risk] 收紧普通表单参照成功条件后，之前被绿灯掩盖的用例会失败。→ Mitigation: 这是目标行为；失败信息必须指向未确认关闭或未回填，方便修运行时或业务数据。
- [Risk] 过度收紧会破坏“点击候选即自动关闭”的合法参照。→ Mitigation: 自动关闭仍可成功，但必须能证明字段回填且候选层真实不可见。
- [Risk] 误把可编辑表格性能修复回滚。→ Mitigation: 将早退兜底限定在可编辑表格路径，并用既有 scalar unique / editable popup 回归覆盖。
- [Risk] 跨 iframe 可见性判断变慢。→ Mitigation: 保留短超时扫描，但失败时继续进入确认或诊断，不把扫描失败当作隐藏成功。
