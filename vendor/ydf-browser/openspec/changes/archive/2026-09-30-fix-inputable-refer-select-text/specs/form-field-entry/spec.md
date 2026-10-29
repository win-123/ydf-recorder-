## ADDED Requirements

### Requirement: 可输入页面参照支持标量文本录入

系统 SHALL 在 `form.fill` 处理 `YDFReferSelect` 时，对 `props.referType` 为 `uidata` 或 `link` 且 `props.caninput` 明确开启的字段，将标量目标作为自由文本录入；系统 MUST 在失焦后确认实际值，不能要求文本已存在于参照候选中。

#### Scenario: 新摘要不依赖已有候选
- **WHEN** 表单中的页面参照允许自由输入，DSL 为其提供新的标量字符串
- **THEN** 系统 MUST 录入该字符串并在失焦后确认实际值
- **AND** 系统 MUST NOT 打开参照弹窗要求选择已有候选

#### Scenario: 结构化目标继续选择参照
- **WHEN** 同一可输入字段收到 `first_available`、`match` 或其它结构化参照目标
- **THEN** 系统 MUST 使用既有参照选择及回填确认流程

#### Scenario: 非自由输入参照保持原有语义
- **WHEN** 字段未明确开启 `caninput`、不属于页面参照模式，或组件为树参照或表格参照
- **THEN** 系统 MUST 保持既有候选选择和回填要求

#### Scenario: 失焦后未保留输入值时失败
- **WHEN** 自由文本已输入，但失焦后实际值与目标值不一致
- **THEN** 系统 MUST 将字段录入判定为失败并报告实际值
