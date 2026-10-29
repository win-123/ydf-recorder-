## Context

当前 `popup-reference-tree-table-selection` 已经要求树表参照支持 `保存/取消` 式页脚确认。历史修复覆盖了普通弹窗根：运行时能选中右侧 WUI 表格候选行，并点击弹窗内 `保存` 后返回。

本次真实用例 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-项目库-YDF-82797-0001-执行项目新增父子项目和设置经费管理员.yaml` 暴露了另一个形态：`项目负责人` 参照打开的是 `PM_SELECT_MANAGER` iframe 前景页。运行时选中 `人员二十一` 后，报告记录 `confirmed=false`，后续 `tab.click 财务核算信息` 失败时仍存在 `BillRender?code=PM_SELECT_MANAGER...&_fromNodeCode=proManager` frame，截图显示参照框和右下角 `保存` 仍可见。

关键约束：

- `保存` 已是合法弹出参照确认标签，不能重新设计 DSL。
- 参照选择流程必须继续支持自动关闭或点击候选即回填的既有场景。
- 关闭判断必须扫描主页面和子 frame，不能只依赖最初解析出的 locator 是否仍可见。
- 真实完成标准是当前 YAML 至少越过 `项目负责人` 后的 `tab.click 财务核算信息`。

## Goals / Non-Goals

**Goals:**

- 在选中参照候选后，如果前景 iframe/非标准弹框仍有候选内容和 `保存/取消` 页脚，运行时 MUST 继续点击当前参照内的 `保存`。
- 避免 `_popup_reference_dialog_hidden_now()` 对仍可见的参照框返回关闭状态。
- 结果报告在成功确认时记录 `confirmed=true` 和 `confirm_label=保存`。
- 用单元测试覆盖关闭检测假阳性，并用真实 YAML 验证修复路径。

**Non-Goals:**

- 不新增 DSL 字段，也不要求用例显式写 `confirm_label: 保存`。
- 不重构全部弹窗定位体系。
- 不改变普通 `YDFSelect`、`YDFTreeSelect` 或查询区普通下拉的选择逻辑。
- 不解决该 YAML 后续可能出现的业务数据、保存校验或子项目流程问题；本 change 只保证项目负责人参照确认链路正确。

## Decisions

1. 以“当前是否仍存在可见参照前景层”为关闭判断依据。

   `_popup_reference_dialog_hidden_now()` 不能只检查传入 `dialog` 根内是否存在 overlay selector。对于 iframe 式参照，传入根可能是结构探测出的内容容器，真实前景层表现为独立 frame 或普通容器。实现应在所有搜索上下文中识别可见的参照选择面：候选树/表格/列表 + `保存/确定/确认` 确认按钮 + `取消` 或参照标题等参照特征。

   替代方案是要求 YAML 写 `confirm_label: 保存`。这只能绕开一部分路径，无法修复“运行时误判弹框已关闭”的根因，也会破坏 `保存` 已是默认确认标签的既有语义。

2. 选择后仍可见时继续走现有确认点击路径。

   `_select_popup_reference()` 已有确认分支和失败诊断，应该让 iframe 前景参照落入该分支，而不是新增旁路。这样可以复用 `保存` 选择、关闭等待、二次激活和报告字段。

   替代方案是在候选点击后立即强制点击 `保存`。风险是破坏点击候选即自动关闭的参照，因此仍应先通过可靠关闭检测判断是否需要确认。

3. 报告字段作为验收信号。

   对该问题，`confirmed=false` 是明确的错误信号；修复后项目负责人字段应报告 `confirmed=true`、`confirm_label=保存`。这比只看后续步骤通过更便于定位回归。

## Risks / Trade-offs

- [Risk] 全局扫描所有 frame 可能误把背景编辑页底部 `保存` 当成参照确认。→ Mitigation: 仍要求同一候选根/前景层内同时存在参照选择面和确认按钮，并优先限制在当前弹出参照上下文。
- [Risk] 放宽关闭检测可能让已经关闭但字段回填慢的场景多等待一次。→ Mitigation: 保留字段回填等待和弹框关闭等待的短超时，不改变成功路径的最终语义。
- [Risk] iframe 参照 DOM 形态在不同环境略有差异。→ Mitigation: 回归测试覆盖运行时判定逻辑，真实验证使用 t9i 的 YDF-82797 YAML 和报告/截图证据。
