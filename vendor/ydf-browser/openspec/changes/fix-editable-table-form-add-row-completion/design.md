## Context

executor 已经在调用 runtime 前清空 pending dynamic template，并在 runtime 返回后等待、应用行编辑表单模板。当前断点位于 runtime：浏览器脚本点击正确新增入口后，如果目标表格仍为空态便返回 `null`，导致 executor 无法执行已有的动态模板完成判定；搜索循环还会继续在指向同一文档的 frame/page 上再次执行脚本。

## Goals / Non-Goals

**Goals:**

- 保留一次新增点击的候选、目标作用域和前后行状态，即使该点击只打开行编辑表单而没有立即增行。
- 继续由 executor 统一裁决“真实增行”或“行编辑表单打开”两种完成信号。
- 在已发生点击副作用后停止跨搜索上下文继续执行。

**Non-Goals:**

- 不新增 DSL 字段，不改变 `target.editor` 的取值。
- 不在 runtime 中复制动态模板解析逻辑或传入新的 editor 参数。
- 不放宽无增行、无动态模板时的失败门禁。

## Decisions

1. 浏览器新增脚本在候选已经点击、但行状态未变化时返回结构化结果，而不是返回 `null`。

   结果沿用现有 `row_state_before`、`row_state`、`row_state_changed`、`row_state_reliable`、`validation_root` 和 `chosen_candidate` 字段。搜索循环收到该结果后立即停止，因此同一文档不会因 frame/page 重复上下文再次点击。相比在 Python 层解析 debug 并合成结果，这能让点击结果只有一个结构化出口。

2. executor 在动态模板判定之后统一执行未增行失败门禁。

   runtime 返回可靠的 `row_state_changed=false` 时，executor 仍先等待 pending dynamic template。动态模板存在则按既有 `可编辑表格新增行表单已打开` 成功；动态模板不存在则无论点击前是否已有数据行都报告新增未生效。这样同时覆盖空表和非空表，不需要页面特例。

3. 保持 editor 语义只在 executor 层。

   `target.editor: form` 继续控制动态模板等待和“必须打开表单”的约束；runtime 只报告发生了什么，不推断 DSL 期望。相比给 runtime 增加 editor 参数，该边界改动更小，也避免两个模块重复判断完成语义。

4. 回归测试分别锁定 runtime 副作用和 executor 完成裁决。

   真实 Playwright DOM 测试覆盖空表、稳定 fieldid 新增入口、表单弹出、结构化未增行结果和单次点击；executor 聚焦测试覆盖该结果与 pending dynamic template 组合后的成功，以及没有动态模板时的失败。

## Risks / Trade-offs

- [Risk] 返回未增行结果后，调用方可能误把“点击完成”等同于“新增成功” → executor 对无动态模板的 `row_state_changed=false` 保持失败，测试覆盖空表和非空表。
- [Risk] 动态模板到达慢于 runtime 返回 → 保留 executor 现有的有界 pending dynamic template 等待，不增加固定睡眠。
- [Risk] 某些页面点击后同时延迟增行并打开表单 → 两种完成信号任一成立即可继续，报告优先保留动态模板摘要和行状态证据。
