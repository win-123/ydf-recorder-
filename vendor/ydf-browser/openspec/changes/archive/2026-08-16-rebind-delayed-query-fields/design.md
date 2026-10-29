## Context

参见 `proposal.md` 的问题背景。当前 `tab.click` 在收到 `tab_active` 后捕获一次运行时元素并重建 binding，但 YonDiF 页签内容可能继续异步渲染。`query.search` 随后发现字段缺失时，会先依据 manifest 中的稳定编辑动作拒绝运行时兜底，因此没有机会重新绑定 manifest 已声明、但稍后才出现的查询输入。

## Goals / Non-Goals

**Goals:**

- 在共享 `query.search` 入口恢复延迟出现的 manifest 查询字段。
- 保留查询字段与编辑表单字段的作用域隔离。
- 只在 manifest 已声明但当前未绑定的目标字段上增加有限等待。

**Non-Goals:**

- 不改变 `tab_active` 完成信号的定义，也不为所有页签增加固定等待。
- 不改变 runtime-only 查询字段的既有兼容兜底。
- 不处理 `action.click` 打开参照时的模板恢复判断。

## Decisions

1. **先做 manifest-aware 刷新，再执行防误绑判断。** 当目标名称能匹配 `current_manifest.query_fields` 时，executor 使用现有 `_refresh_current_binding()` 和 `_wait_for_runtime_settle()` 在有限时间内重试 `_query_field_candidates()`。这样优先恢复平台模板声明的精确查询字段，不放宽运行时文本猜测。
2. **仅对已声明查询字段等待。** 名称不属于 manifest 查询字段时沿用当前快速失败和 runtime-only 兼容路径，避免错误 DSL 平白等待。
3. **复用表单重绑定的轮询形状。** 查询字段采用与 `_refresh_binding_until_form_field()` 相同的 5 秒上限和 300 毫秒间隔，只新增查询候选判定，不引入通用重试框架。

备选方案是在 `tab.click` 后固定 sleep，因其会拖慢所有页签且不能保证覆盖渲染时序而不采用；保存后重新 `open_menu` 只作为临时 DSL 规避，不作为运行时修复。

## Risks / Trade-offs

- [声明存在但始终不渲染的查询字段最多增加约 5 秒失败延迟] → 仅在精确 manifest 查询字段缺失时轮询，并在命中后立即返回。
- [错误地放宽到普通表单字段] → 刷新后仍使用 `_query_field_candidates()` 的查询区分类，既有稳定编辑动作保护保持不变。
