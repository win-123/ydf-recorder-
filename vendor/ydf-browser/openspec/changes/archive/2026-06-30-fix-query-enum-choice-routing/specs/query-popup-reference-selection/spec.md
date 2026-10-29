## ADDED Requirements

### Requirement: 普通枚举查询条件保持下拉行为
系统 SHALL 在 `query.search` 中将普通枚举查询字段识别为 choice/dropdown 字段，并使用普通下拉候选选择流程录入查询值。

#### Scenario: 单据类型查询选择调拨
- **WHEN** 用例在 `query.search` 中填写 `单据类型 = 调拨`
- **AND** 当前查询字段模板组件为 `LCDEnum` 或 raw 元数据包含非空 `enumType`
- **AND** 该字段未声明为 modal/reference 参照字段
- **THEN** 运行时 MUST 使用普通 choice/dropdown 候选选择逻辑选择 `调拨`
- **AND** 运行时 MUST NOT 调用弹出参照选择流程
- **AND** 运行时 MUST NOT 报告 `未打开弹出参照选择框`
- **AND** 如果页面未将查询字段提交为 `调拨`，运行时 MUST 让该步骤失败并报告 choice/dropdown 诊断
