## Context

`YDFDateRange` 在模板中是普通 `formItem`，当前问题字段为 `对账起止日期`，组件名 `YDFDateRange`，业务 DSL 写法为 `对账起止日期: "2026-01-01~2026-01-12"`。现有 runtime 只按 probe 中包含 `date` 判断日期字段，导致日期范围控件可能复用普通 `YDFDatePicker` 的强写路径，把值写到外层节点属性而不是组件真实输入状态。

本变更继续沿用 `form.fill` 字段级语义，避免新增面向控件实现的 DSL action。

## Goals / Non-Goals

**Goals:**

- 支持 `YDFDateRange` 使用标量区间字符串录入，格式为 `YYYY-MM-DD~YYYY-MM-DD`，允许 `~` 两侧有空格。
- runtime 必须真实作用于日期范围控件内部状态，不能把外层节点的自写 `value/title` 当作成功。
- 写后确认必须读取真实可见值、真实 input 值或能证明保存不再触发该字段必填错误的结果。
- 报告中保留归一化后的 `actual`、目标 `selector` 或字段身份、`confirmed`。

**Non-Goals:**

- 不新增 `date_range.*` DSL 组件。
- 不在本变更引入相对日期、动态日期表达式或日期时间范围。
- 不改变普通 `YDFDatePicker`、下拉、参照、开关、单选的 DSL 写法。

## Decisions

1. 保留当前标量 DSL 写法。

   `对账起止日期: "2026-01-01~2026-01-12"` 是最短、最贴近业务的表达。结构化写法如 `{start, end}` 暂不引入，等出现变量组合、日期时间或多种范围格式时再扩展。

2. 在 runtime 中优先识别 `YDFDateRange`，再处理普通日期字段。

   `YDFDateRange` 与 `YDFDatePicker` 的交互和确认条件不同。日期范围必须从普通 `_set_date_field_value` 路径分离，避免外层 `div` 被误写后产生假确认。

3. 录入优先复用运行时 fieldid 和前景字段根定位。

   模板已能生成 `<父容器divCode>_<dataField>`、`_input`、`_suffix` 候选。实现应先利用这些身份找到当前前景字段，再打开日期范围控件并选择开始、结束日期。

4. 确认以真实控件状态为准。

   成功条件必须来自真实可见文本、真实 input value、组件内部可读值，或真实保存后未再触发该字段必填错误。仅对外层根节点写入属性并读回不得算成功。

## Risks / Trade-offs

- [Risk] 不同 YonDiF 版本的日期面板 DOM class 可能不同 -> Mitigation: 选择器覆盖 `wui`、`w`、`ant` 常见面板，并以可见弹层内精确日期文本为主。
- [Risk] 同页存在多个日期弹层或背景字段 -> Mitigation: 打开目标字段后只在当前可见前景弹层内选择日期，并继续使用前景字段根规则。
- [Risk] 只验证 DOM 回填仍可能漏掉后端字段拆分错误 -> Mitigation: 真实用例验证需要包含保存或等价业务确认，证明不再报 `对账起止日期` 必填。
