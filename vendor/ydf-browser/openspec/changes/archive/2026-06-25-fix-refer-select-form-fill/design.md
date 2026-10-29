## Context

真实用例 `/Users/ken/temp/ydf-browser-问题反馈/功能-单位资金代管-预算支付全景-新增-普通转账-001 (1).yaml` 在 `form.fill` 填写 `结算方式` 时失败。模板字段的组件名是 `YDFSelect`，但 raw 元数据声明 `refuri` 参照定义；当前 runtime 先把 `YDFSelect` 归入普通 choice，下拉候选不存在时失败。

截图还显示该字段默认值已经是 DSL 目标值 `1 电子转账支付`。因此这个修复需要同时覆盖参照判型和已有值幂等录入。

## Goals / Non-Goals

**Goals:**

- 让 `form.fill` 对 `refuri` 等明确参照元数据优先走 popup reference 语义。
- 让表单字段当前可见值已匹配 DSL 目标值时直接成功，不重复打开下拉或参照。
- 保留普通枚举、普通下拉和 `caninput` 参照字段的既有行为。

**Non-Goals:**

- 不新增 DSL 语法。
- 不重构全部字段绑定逻辑。
- 不承诺本支付用例后续保存、签章或业务校验一定通过。

## Decisions

- 在 runtime 字段判型中优先判断 raw `refuri` 参照元数据，再处理组件名中的 `select`。这样 `YDFSelect + refuri` 不会被普通 choice 分支截走。
- 已有值匹配使用现有字段读值和文本等价判断，不新增页面专用规则。目标是覆盖默认值、回填值和显示值中包含编码加名称的常见情况。
- `caninput` 参照字段继续允许标量值按文本输入，结构化目标仍走 popup reference。

## Risks / Trade-offs

- 参照元数据过宽可能把普通 `YDFInput` 字段转入 popup reference。缓解方式是只认 `refuri` 这类明确 raw 参照信号，不因单纯 `dataType=refer`、`enty`、类名或箭头推断。
- 已有值短路可能掩盖字段绑定到错误节点。缓解方式是仍依赖当前绑定根读值；测试覆盖目标字段身份和目标值匹配。
