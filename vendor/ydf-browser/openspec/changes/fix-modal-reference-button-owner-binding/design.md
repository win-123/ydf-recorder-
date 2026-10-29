## Context

真实采购计划行编辑表单中，`YDFTableModalSelect` 的节点 `divCode` 被多个包装节点继承；只读输入不可操作，唯一可用入口是同一 `uikey` 根内的按钮。需求调查登记中的 `YDFTreeModalSelect` 则在同一根内同时暴露唯一可编辑输入和参照按钮。binder 必须按控件能力区分这两种形态，runtime 仍从来源字段或目标单元格证明回填。

## Goals / Non-Goals

**Goals:**

- 让标准表格、树弹出参照在同根唯一按钮形态下通过精确身份绑定。
- 继续从来源字段 owner 打开参照并确认回填。
- 保留多按钮、多 owner、背景实例和不可接收 pointer 状态的失败关闭语义。

**Non-Goals:**

- 不把普通按钮或任意 `refer` 文本候选放宽为表单字段。
- 不改变弹出参照过滤、候选匹配、确认或 DSL 结构。
- 不为采购计划页面增加专用 fieldid 或页面分支。

## Decisions

1. 在 binder 的“直接控件”和“平台身份可用性”两处加入同一组件限定判定。仅 `YDFTableModalSelect`、`YDFTreeModalSelect` 的 `button`，且 `visible=true`、`disabled=false`、`pointer_receivable=true` 时成立；按钮的 `editable=false` 不再使参照触发器失效。相比修改全局 DOM 扫描的 editable 含义，此方案不会影响工具栏、普通按钮和包装节点。
2. 在 `_collapse_same_root_exact_matches` 内先检查同根非按钮直接控件：恰好一个时优先返回该输入；没有非按钮直接控件时沿用唯一按钮规则；多个输入或多个按钮仍返回不兼容。该能力优先级同时覆盖按钮-only 和 input + button 两种真实组件形态，不增加评分或页面特例。
3. runtime 已识别目标为弹出参照时，先复用现有前景字段根解析；只有无法恢复 owner 时才沿用 pointer root 路径。这样按钮负责触发，字段根负责初值与回填读取，也保持普通文本、choice、switch 的现有顺序。
4. 回归分两层：binder 测试锁定唯一按钮与多按钮边界；runtime 测试锁定 owner 优先级。最终由原始真实 DSL 证明参照选择、确认和字段回填完整通过。

## Risks / Trade-offs

- [Risk] 某些自定义参照使用非 `button` 触发器 → Mitigation：保留现有派生输入和兼容路径，本次不扩大组件或标签范围。
- [Risk] 背景存在同 key owner → Mitigation：继续依赖前景字段根、可见性、pointer 和现有精确身份门禁；真实验证检查最终回填。
- [Risk] 只修绑定后按钮成为回填根 → Mitigation：runtime 回归明确要求 popup reference 优先恢复字段 owner。
- [Risk] input + button 被误判为两个等价控件 → Mitigation：binder 回归要求唯一可编辑 input 优先，按钮仅作为无可用输入时的触发入口。
