## Context

`form.assert_values` 目前主要覆盖文本、选择类、switch 和 radio 字段。普通 `YDFCheckbox` 在模板中是 `formItem`，真实 DOM 可能表现为 `label[fieldid=...]`、checkbox wrapper、隐藏或不可见 `input[type=checkbox]`、`aria-checked` 或 checked class。当前运行时没有把普通 checkbox 当作可读状态控件处理，字段根解析也常把 checkbox 从可编辑控件候选里排除。

真实复现用例是 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-预算批复-YDF-77108.yaml`。执行到 `支出计划信息` 页签后，`隐藏0金额行: "on"` 失败为 `actual='序号'`。报告显示模板中存在两个同名字段：`hideZero` 位于 `支出计划信息`，`hideZeroBgt` 位于 `项目预算信息`，二者都是 `YDFCheckbox`，且 `dataField` 和 `property_uri` 都相同。因此本变更需要同时解决 checkbox 状态读取和同名跨页签字段解析。

## Goals / Non-Goals

**Goals:**

- 让 `form.assert_values` 可以对普通表单 `YDFCheckbox` 断言勾选/未勾选状态。
- 将 checkbox 读取从通用文本兜底中分离出来，避免读取邻近表格表头、字段标签或容器文本。
- 支持用户以 `on/off`、`true/false`、`1/0`、`是/否` 等等价值表达 checkbox 期望状态。
- 在同名、同 `dataField`、同 `property_uri` 的多个 checkbox 候选中，优先选当前活动页签或当前可交互区域内的字段。
- 在步骤报告中输出稳定的 canonical 状态和命中字段身份，便于真实页面排查。

**Non-Goals:**

- 不改变 `YDFSwitch` 的 `是/否` 读写语义。
- 不把表格行选择 checkbox、表头全选 checkbox、树节点 checkbox 归入普通表单字段。
- 不新增 DSL action；仍使用现有 `form.assert_values`。
- 不要求 `form.fill` 在第一阶段完整支持普通 checkbox 勾选/取消；本变更先解决断言读取，若实现中复用同一状态 helper 支持填充也应保持兼容。

## Decisions

1. checkbox 断言采用 canonical `on/off` 状态，比较时接受别名。

   运行时读取普通 checkbox 字段时返回 `on` 或 `off`。执行器比较期望值时将 `on/true/1/yes/y/是/勾选/已勾选/选中/checked` 归为 checked，将 `off/false/0/no/n/否/未勾选/不勾选/未选中/unchecked` 归为 unchecked。这样既兼容当前用例里的 `"on"`，也允许中文业务写法。

2. checkbox 状态读取必须优先于通用字段文本读取。

   `read_field_value()` 在识别 candidate 或 runtime 为 checkbox 后，应直接解析 `input.checked`、`aria-checked`、`checked`/`selected` class、常见 wui/ant/u checkbox wrapper，而不是先尝试 `input.value` 或容器文本。若字段被识别为 checkbox 但无法确定状态，应返回明确错误或空诊断，不应回退为 `序号` 这类无关文本。

3. 表单字段根定位应把 checkbox 纳入“控件”范围，但排除表格和树选择场景。

   `_resolve_form_field_root_by_label_position()`、`_narrow_form_field_root()` 和运行时元素采集中的控件 selector 需要包含普通 checkbox wrapper/input。过滤条件必须继续排除 `runtime.in_table`、树节点、表格行选择列和表头选择列，避免把选择行能力误识别成表单字段。

4. 同名字段解析以当前运行时状态为准。

   当多个候选字段同名且都非表格/查询字段时，executor 不应只按模板顺序或 `property_uri` 返回第一个。候选排序需要考虑当前 runtime 绑定是否真实可见、是否能读取 checkbox 状态、是否在当前活动页签内容区内，以及 fieldid 是否与可见 DOM 身份一致。`tab.click` 后的断言应分别命中 `hideZero` 和 `hideZeroBgt`。

5. 报告保持可诊断。

   `form.assert_values` 成功报告继续输出 `field`、`equals`、`actual`、`fieldid`、`property_uri`。对 checkbox 字段，`actual` 使用 `on/off`；如实现能获得原始状态来源，可附加 `value_source` 或类似诊断，但不是 DSL 合同必需项。

## Risks / Trade-offs

- [Risk] 部分页面使用 checkbox class 但实际是表格选择控件。→ Mitigation: 普通表单 checkbox 识别必须结合模板 candidate、非 table runtime、formItem 区域和字段标签，表格/树选择继续走专用路径。
- [Risk] 隐藏页签 DOM 仍被框架标记为 visible。→ Mitigation: 候选选择除了 `is_visible()`，还需要评估当前页签内容区、可接收 pointer/有尺寸交集、或状态控件所在容器是否处于活动 tab panel。
- [Risk] checkbox 的 DOM 状态来源不统一。→ Mitigation: 读取顺序覆盖原生 input、`aria-checked`、常见 checked class，并保留调试输出，真实回归以 YDF-77108 用例为准。
- [Risk] `on/off` canonical 与 switch 的 `是/否` 不一致。→ Mitigation: 只对普通 checkbox 使用 `on/off`；switch 仍保持既有 `是/否`，避免破坏已有开关断言。

## Migration Plan

这是向后兼容扩展。已有 `form.assert_values` 文本、select、switch、radio 断言不需要迁移。新增文档只说明普通表单 checkbox 可使用 `on/off` 和中文等价值断言状态。

## Open Questions

- 是否在同一 change 中补齐 `form.fill` 对普通 checkbox 的勾选/取消支持。建议实现阶段先以 `form.assert_values` 为验收边界；如果状态 helper 很自然复用到填充，可作为同一任务的非破坏性增强。
