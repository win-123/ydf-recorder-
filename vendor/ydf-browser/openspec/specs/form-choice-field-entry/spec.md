# form-choice-field-entry Specification

## Purpose
定义普通表单 choice/dropdown 字段在 `form.fill` 中的控件识别、候选选择、弹出参照边界和失败诊断，确保 `LCDEnum` 等枚举字段按普通下拉语义录入。

## Requirements
### Requirement: Form fill treats enum fields as choice fields
系统 SHALL 将普通表单枚举字段识别为 choice/dropdown 字段，并使用普通下拉候选选择流程完成 `form.fill`。

#### Scenario: LCDEnum source mode selects purchase
- **WHEN** DSL 执行 `form.fill`，目标字段为 `来源方式: 采购`
- **AND** 当前模板字段组件为 `LCDEnum`，字段元数据包含 `enumType=ammSourceMode`
- **AND** 运行时下拉候选中存在显示文本 `采购`
- **THEN** 系统 MUST 点击或激活该普通下拉字段并选择 `采购`
- **AND** 系统 MUST 将该字段录入判定为成功

#### Scenario: enumType metadata is enough for choice classification
- **WHEN** `form.fill` 目标字段模板 raw 元数据包含非空 `enumType` 或等价枚举类型声明
- **AND** 该字段未声明为 modal reference、table modal select、tree modal select 或 radio/switch/date 控件
- **THEN** 系统 SHALL 将该字段交给普通 choice/dropdown 选择流程

### Requirement: Plain choice fields do not open popup references
系统 MUST 在普通表单 choice/dropdown 字段中避免仅因存在下拉箭头、select arrow 或 dropdown arrow 就打开 popup reference 流程。

#### Scenario: LCDEnum arrow does not trigger popup reference
- **WHEN** `LCDEnum` 字段根节点内存在可见下拉箭头
- **AND** 用例通过 `form.fill` 填写标量值
- **THEN** 系统 MUST NOT 调用 popup reference 选择流程
- **AND** 系统 MUST NOT 报告 `未打开弹出参照选择框`

#### Scenario: Modal reference fields remain popup references
- **WHEN** `form.fill` 目标字段组件为 `YDFTableModalSelect`、`YDFTreeModalSelect`，或组件名明确包含 `refer`、`reference`、`modalselect`
- **THEN** 系统 MUST 继续使用 popup reference 选择流程
- **AND** 普通枚举 choice 识别 MUST NOT 允许表格参照字段使用未结构化的标量文本绕过已有校验

### Requirement: Choice failures report choice diagnostics
系统 SHALL 在普通枚举字段候选无法选择时报告 choice/dropdown 诊断，而不是 popup reference 弹窗缺失诊断。

#### Scenario: Missing enum option reports dropdown context
- **WHEN** `form.fill` 目标字段被识别为普通枚举 choice 字段
- **AND** 运行时未找到期望候选值
- **THEN** 当前步骤 MUST 失败
- **AND** 错误信息 MUST 指向未找到下拉候选或 choice 候选诊断
- **AND** 错误信息 MUST NOT 使用 `未打开弹出参照选择框` 作为主错误

### Requirement: popup reference 打开后可见普通下拉时回退
系统 SHALL 在 `form.fill` 标量字段误入 popup reference 打开流程后，识别已经可见的普通 choice/dropdown 面板，并改用普通下拉候选选择流程完成录入。

#### Scenario: 可见普通下拉避免弹出参照 dialog 缺失失败
- **WHEN** DSL 执行 `form.fill`，目标字段值为标量文本 `1 普通业务`
- **AND** 运行时点击字段或字段触发器后没有新增弹出参照 dialog
- **AND** 当前运行时存在可见 `.wui-select-dropdown`、`.w-select-dropdown`、`.ant-select-dropdown`、`.u-select-dropdown` 或 `[role="listbox"]` 普通下拉面板
- **THEN** 系统 MUST 使用普通 choice/dropdown 候选选择流程选择目标值
- **AND** 系统 MUST NOT 报告 `未打开弹出参照选择框`

#### Scenario: 结构化弹出参照目标不使用普通下拉回退
- **WHEN** DSL 执行 `form.fill`，目标字段值为结构化弹出参照目标
- **AND** 运行时进入 popup reference 打开流程
- **THEN** 系统 MUST 继续使用弹出参照选择流程
- **AND** 系统 MUST NOT 使用普通下拉 fallback 绕过结构化参照语义
