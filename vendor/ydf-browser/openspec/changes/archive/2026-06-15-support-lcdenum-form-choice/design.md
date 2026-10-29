## Context

`form.fill` 目前会先判断 switch/radio，再判断普通 choice/dropdown，再判断 popup reference。既有保护已经让 `YDFSelect`、`YDFTreeSelect` 这类普通选择控件优先走 choice 分支，避免被 `refCode` 等元数据误送进弹出参照流程。

这次真实失败来自 `入库填报` 新增页：`来源方式` 模板组件为 `LCDEnum`，字段 `sourceModeCode`，元数据包含 `enumType=ammSourceMode`。运行时打开后页面出现 `.wui-select-dropdown`，候选包括 `采购`，但 `_looks_like_choice_field()` 没有识别 `LCDEnum`，随后 `_looks_like_popup_reference_field()` 通过普通下拉箭头命中 `_root_has_popup_reference_trigger()`，错误调用 `_select_popup_reference()`。

## Goals / Non-Goals

**Goals:**

- 让 `form.fill` 对 `LCDEnum` 和带 `enumType` 的普通表单字段走现有 choice/dropdown 选择流程。
- 保持 DSL 写法不变：`来源方式: 采购` 应继续表示选择显示文本为 `采购` 的候选。
- 维持 popup reference 和普通 choice 的边界，避免普通下拉箭头触发参照流程。
- 用单元测试覆盖分支选择，用真实 YAML 验证当前失败点解除。

**Non-Goals:**

- 不新增 DSL schema 或 `form.enum.*` 组件语法。
- 不改 popup reference 结构化选择语义。
- 不处理当前 YAML 后续可能暴露的物资明细字段写法或业务校验问题；这些应按独立失败另行判断。
- 不重构所有控件分类逻辑，只做与普通表单 choice 判断相关的最小闭环。

## Decisions

1. 在 choice 识别层支持枚举元数据，而不是为 `来源方式` 做字段名特判。

   推荐方案是扩展 `_looks_like_choice_field()`：当模板组件名归一化后为 `lcdenum`，或候选 raw 元数据存在非空 `enumType` / `enum_type` 时，将其识别为普通 choice。这样覆盖 YonDiF 枚举控件族，而不是绑定到 `来源方式` 或 `ammSourceMode`。

   备选方案 A 是从 popup reference 触发器中移除 `arrow` 标记。风险是可能破坏部分真实参照控件只暴露箭头/放大镜类入口的页面。备选方案 B 是在 `_looks_like_popup_reference_field()` 中排除 `LCDEnum`，但这只能阻止误走参照，仍不能确保它进入正确的 choice 选择流程。

2. 保留现有 choice 选择实现。

   当前 `build_query_choice_selectors()` 已覆盖 `.wui-select-dropdown :text-is("<value>")`、`[title="<value>"]` 等候选形式，诊断截图也证明真实候选已渲染在 `.wui-select-dropdown` 中。因此实现应复用 `_select_query_choice()`，不新增枚举专用点击流程。

3. 保持 popup reference 显式组件优先级。

   `YDFTableModalSelect`、`YDFTreeModalSelect`、组件名包含 `refer/reference/modalselect` 的字段仍应走 popup reference。枚举识别只应覆盖普通 choice 控件，不得让表格参照接受标量文本，避免绕过已有结构化 match 要求。

## Risks / Trade-offs

- [Risk] 某些页面可能存在名称非标准但带 `enumType` 的非下拉字段。→ Mitigation: 只在 `form.fill` 普通表单字段路径中应用，并保留 radio/switch/date 优先判断；实际候选仍必须能在下拉面板中选择，否则按 choice 诊断失败。
- [Risk] 真实 YAML 越过 `来源方式` 后可能在后续 `editable_table.fill_row` 或保存步骤失败。→ Mitigation: 验证报告中只把“当前失败点解除”作为本 change 的完成标准，后续独立失败另行记录。
- [Risk] 调整控件分类可能影响已有 select/tree select。→ Mitigation: 运行现有 runtime 回归，特别关注 `YDFSelect`、`YDFTreeSelect`、popup reference 和 radio/switch 相关测试。
