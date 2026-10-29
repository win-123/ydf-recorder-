## Context

`editable_table.add_row` 当前由 executor 解析 `target.table` 为模板表格身份，再把 `table_fieldid` 和列身份传给 runtime。runtime 的 add-row 脚本在目标表格作用域内选中 `新增` 候选，点击一次后读取目标表格行状态；如果非空表格行数没有增长，executor 按现有规格失败。

这套门禁保护了“不能把同一行重复交给后续 fill_row”的正确性。当前问题不是门禁过严，而是连续 `editable_table.fill_row -> editable_table.add_row` 时，上一轮填行可能留下激活编辑态、选择下拉或行级悬浮/更多按钮状态。下一次点击 `新增` 可能先被页面用于提交、失焦或关闭悬浮层，导致行数未增长。

## Goals / Non-Goals

**Goals:**

- 在 `add_editable_table_row` 点击新增入口前，用共享 runtime 逻辑收口当前可编辑表格交互状态。
- 当目标表格已解析出 `table_fieldid` 时，优先点击 `${table_fieldid}_add_button` 对应的可见 fieldid 入口。
- 在目标表格已有真实数据行、首次点击未增长且未打开行编辑表单模板时，只在同一目标表格作用域内重试一次。
- 保留目标表格限定验证和行数增长门禁，失败时继续输出可定位的行数和目标表格诊断。
- 用聚焦测试和真实 DSL 证明连续新增、填行、再新增链路通过。

**Non-Goals:**

- 不改变 DSL schema、`target.table` 写法或用户可见语义。
- 不放宽 `editable_table.add_row` 成功标准，不把未增长的行状态当成功。
- 不新增页面特例或按菜单名硬编码采购需求编制页面。
- 不处理业务数据本身导致的新增失败；重试后仍不增长仍按运行时失败报告。

## Decisions

1. 在 runtime 的共享新增入口处理，而不是在 DSL 或具体页面绕过。

   所有 `editable_table.add_row` 都经过 `PlaywrightRuntime.add_editable_table_row`，这里能复用目标表格身份、候选选择和行状态验证。把修复放在 DSL 用例或 executor 特例里会让同类页面继续失败。

2. 优先使用表格 fieldid 派生的新增入口。

   采购需求编制页面中 `table_fieldid=cgbd_table` 的新增操作入口稳定暴露为 `fieldid="cgbd_table_add_button"`。runtime 已经从模板表格解析出 `table_fieldid`，因此可先查找 `${table_fieldid}_add_button` 对应的可见 fieldid 入口，命中后作为最高优先级候选。该路径不要求 DSL 新增字段；当页面没有这个派生 fieldid 时继续走原有文本和表格作用域候选扫描。

3. 点击前做轻量交互收口。

   运行时应优先执行不会改变业务数据的收口动作：让当前 active element blur、派发 focusout/blur、关闭可见选择下拉、把鼠标移出行级悬浮区，并等待短暂稳定。这样处理的是“上一个编辑态挡住下一次新增”的根因，不改变目标表格选择逻辑。

4. 只允许一次受控重试。

   首次点击后如果目标表格已有真实数据行、行数未增长、也没有动态行编辑表单打开，runtime 可以再次解析同一目标表格内的新增候选并点击一次。重试仍不增长时失败，避免无限点击造成重复行或掩盖真实业务限制。

5. 保留现有失败门禁。

   `row_state_changed=false` 对非空表格仍然是失败信号。修复只提高点击前后交互稳定性，不把失败改成成功。

## Risks / Trade-offs

- 重试可能在少数慢页面上产生重复点击风险 -> 只在首次点击未观察到目标表格行数增长且未打开动态模板时重试一次，并重新读取目标表格 root。
- blur/focusout 可能触发表格公式或校验 -> 这是人工连续操作也需要发生的提交动作，且当前问题正需要先提交上一格编辑态。
- 诊断仍可能不足以知道首次点击被谁吞掉 -> 在重试路径中保留首次和最终 row_state、目标表格身份和候选摘要，必要时再补截图诊断。
