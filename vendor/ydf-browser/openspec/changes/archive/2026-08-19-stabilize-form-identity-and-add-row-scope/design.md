## Context

见 `proposal.md`。现有 DOM 扫描把 CSS 可见性与当前视口命中混成布尔值；现有表格作用域解析已经为唯一运行时根写入 token，但 `editable_table.add_row` 在进入 JavaScript 后丢弃该 token 并再次猜测验证根。

## Goals / Non-Goals

**Goals:**

- 保留 `true / false / unknown` 三态 pointer 证据，避免把可滚动到达的屏外字段误判为冲突。
- 复用已有表格作用域 token，缩短并收紧新增行验证链路。
- 维持前景优先、同根多输入失败关闭和显式新增一行的既有安全语义。

**Non-Goals:**

- 不为 `YDFTextArea` 增加页面专用 fieldid 后缀规则。
- 不把 `editable_table.add_row` 改成“存在空行时不新增”的条件动作。
- 不处理本次真实用例后续暴露的成员姓名弹出参照打开失败。

## Decisions

1. DOM 控件完全位于视口外时返回 `unknown`，而不是放宽 binder 对 `false` 的过滤。这样视口内明确被遮挡的旧抽屉副本仍然失败关闭；替代方案“所有 pointer=false 都允许绑定”会重新引入背景误填。
2. 对部分进入视口的控件，以可见交集矩形而非完整元素矩形取样 `elementFromPoint`。这样超出视口的一半不会让两个采样点都落在无效坐标。
3. `add_editable_table_row` 仅把已有 `ResolvedTableScope.token` 传给现有脚本，脚本使用唯一可见 token 根；token 不可用时在点击前失败。替代方案是在脚本中继续扩展全页评分，会重复表格作用域解析器已经完成的工作。

## Risks / Trade-offs

- [屏外未知状态可能延迟暴露实际遮挡] → Playwright 实际填充会滚动并在操作阶段失败，且契约标记为未验证，不伪装成精确可达。
- [新增前目标表格整体重渲染并丢失 token] → 在产生点击副作用前失败，由后续动作重新解析表格作用域。
- [页面业务联动预先生成空行] → `add_row` 仍按 DSL 明确语义再增加一行；用例应删除该步骤并直接填写已有第 1 行。
