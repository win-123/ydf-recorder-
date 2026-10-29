## ADDED Requirements

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
