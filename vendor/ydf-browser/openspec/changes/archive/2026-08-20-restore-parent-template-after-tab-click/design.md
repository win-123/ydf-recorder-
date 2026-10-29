## Context

见 [proposal.md](./proposal.md) 的 `Why`。现有动态模板恢复已经集中使用运行时元素、当前 manifest 与上一层 manifest 的可见性评分，但 `tab.click` 完成后只重新绑定当前 manifest。当前子 manifest 自带主表格时，后续表格恢复入口又会把“声明了主表格”误当成仍处于活动工作面。

## Goals / Non-Goals

**Goals:**

- 复用既有 DOM transition 恢复判定，在 `tab.click` 后及时恢复实际可见的父列表 manifest。
- 对页签路径采用严格保留边界：当前动态模板仍有前景稳定动作或可编辑字段时不恢复。
- 让步骤报告明确区分自动恢复与保持当前模板。

**Non-Goals:**

- 不改变 `table_row_selection.select` 的绑定、歧义或失败语义。
- 不新增 DSL 字段、页面特例或固定等待时间。
- 不把背景父列表可扫描视为充分恢复证据。

## Decisions

### 复用现有 DOM transition 恢复入口

扩展既有 transition 判定，使其接受 `tab.click` 来源，并在页签动作完成且无错误通知后调用。该入口已经负责抓取上一层 manifest 的运行时元素、计算当前/上一层可见性评分并执行统一的模板栈恢复，复用它比新增第二套恢复算法更小且能保持报告证据一致。

备选方案是在后续表格选择失败时恢复。该方案只修复表格症状，页签之后的查询、动作和断言仍可能使用过期 manifest，因此不采用。

### 页签恢复必须先排除仍活跃的动态表单

`tab.click` 来源下，只要当前动态 manifest 的稳定动作或可编辑字段仍作为前景身份可见，就保持当前 manifest，不允许仅凭上一层评分更高而恢复。排除该情况后，仍要求上一层评分大于零且严格高于当前评分。

子 manifest 是否声明主表格不作为保留条件；主表格身份必须由动作后的运行时可见性证明。这直接覆盖本次“子 manifest 有表格但 DOM 已回父列表”的根因。

### 恢复结果沿用既有步骤数据

恢复成功时沿用 `restored_template`、`restore_reason: dom_transition` 和 `auto_restored_template: true`；未恢复时只保留已有页签结果，不新增 DSL 或公开结构。

## Risks / Trade-offs

- [页签切换过程中 DOM 尚未稳定导致评分不足] → 沿用 `tab.click` 既有完成等待后再判定，不新增固定睡眠；证据不足时保持当前 manifest。
- [背景父列表元素使评分偏高] → 当前动态模板的前景稳定动作或可编辑字段具有否决权，且父模板评分必须严格占优。
- [扩展共享判定影响已有动作恢复] → 新保护条件仅作用于 `tab.click` 来源，既有 `action.click` 行为保持不变，并用聚焦回归覆盖恢复与保留边界。
