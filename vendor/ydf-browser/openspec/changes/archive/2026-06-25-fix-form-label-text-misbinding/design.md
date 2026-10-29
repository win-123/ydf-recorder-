## Context

真实报告显示，`收款人全称` 的模板字段是 `YDFReferSelect/payeeAcctName`，但绑定到了 runtime 中 `text=开户银行` 的节点；该节点的 `label_text` 被采成 `收款人全称`，且 `in_dialog=true`。当前 `binder._form_candidate_priority()` 先按前景层排序，再按分数排序，导致这个 0.82 分的错误前景候选压过了其它更像目标字段的候选。

同一报告里还出现 `结算方式` 的 `label_text` 串到 `单位内设机构`、多个后续字段带着 `收款人全称` label_text 的现象。问题应在共享绑定层处理，而不是给具体字段加白名单。

## Goals / Non-Goals

**Goals:**
- 阻止 `form.fill` 选择“只靠污染 `label_text` 命中、但 runtime 自身文本明确是另一个字段”的候选。
- 保留已有前景弹窗/抽屉字段优先规则，继续支持审批弹窗 runtime-only 字段。
- 用最小单测覆盖问题形态。

**Non-Goals:**
- 不重写 DOM 扫描器的 `findLabelText()`。
- 不改变 DSL 写法，不新增 selector、层级或字段配置。
- 不调整弹出参照选择流程。

## Decisions

1. 在绑定层过滤明显冲突的 `label_text` 命中。

   当候选的命中原因只来自 `label_text`，并且 runtime 的 `text` 或 `name` 归一化后存在且不等于目标字段名时，将该候选视为串标签候选，不参与该字段绑定。这样一处修复覆盖 `收款人全称 -> 开户银行` 和 `结算方式 -> 单位内设机构` 的同类风险。

   替代方案是改 `runtime.py` 的 `findLabelText()`。该函数服务很多动态表单和审批弹窗场景，直接改 DOM 近邻算法风险更大；本次问题已能在绑定层通过候选自洽性判断拦住。

2. 保留 `label_text` 的正常能力。

   如果 runtime 自身没有明确 `text/name`，仍允许 `label_text` 匹配；审批弹窗扩展字段和无稳定 fieldid 的普通控件依赖这条路径。若存在 `fieldid`、模板 key、`dataField` 等强身份命中，也不因附带的错误 `label_text` 否定候选。

## Risks / Trade-offs

- [Risk] 某些真实控件自身 `text` 包含控件当前值而不是字段标签，可能被误判为冲突。→ Mitigation: 只过滤“命中原因仅来自 `label_text`”的候选；强身份、`aria_label`、`placeholder`、自身文本匹配不受影响。
- [Risk] 前景弹窗字段完全依赖 `label_text` 且自身文本为选中值时可能无法绑定。→ Mitigation: 这类字段应优先暴露 `aria_label`、`placeholder`、`name` 或可由 runtime-only 解析；若没有可靠身份，失败比误填其它字段更安全。
