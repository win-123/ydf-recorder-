## ADDED Requirements

### Requirement: 可编辑表格单元格按身份定位
系统 SHALL 在执行 `editable_table.fill_row` 时优先使用模板列身份定位目标单元格，包括目标列 `fieldid`、`dataField`、所属表格 `fieldid` 和列组件类型。

#### Scenario: 模板身份阻止计量数写入备注
- **WHEN** DSL 文档执行 `editable_table.fill_row`，目标表格为 `项目测算信息`，字段包含 `计量数: "500"`
- **AND** 当前模板中 `计量数` 映射到 `dataField=estVal`，同一表格中 `备注` 映射到 `dataField=activityDesc`
- **THEN** 系统 MUST 激活并写入 `estVal` 对应的行单元格
- **AND** 系统 MUST NOT 将 `"500"` 写入 `activityDesc` 或 `备注` 对应的单元格

#### Scenario: 横向滚动后保持列身份
- **WHEN** 同一个 `editable_table.fill_row` 步骤连续录入多个字段，前一个字段录入导致表格横向滚动或可见列重排
- **THEN** 系统 MUST 在每个字段录入前重新按目标列身份定位单元格
- **AND** 系统 MUST NOT 复用上一次字段的过期单元格、过期表头或过期列索引

#### Scenario: 文本几何兜底保持可用
- **WHEN** 目标页面 DOM 缺少可用于匹配模板列身份的属性
- **THEN** 系统 SHALL 使用现有表头文本和几何映射作为兜底定位方式
- **AND** 系统 MUST 在调试或步骤数据中标记该字段使用了文本几何兜底

### Requirement: 可编辑表格录入诊断
系统 SHALL 在可编辑表格单元格录入成功或失败时暴露足够的列身份和定位来源信息，用于判断实际写入目标是否与 DSL 字段一致。

#### Scenario: 成功录入报告目标身份
- **WHEN** `editable_table.fill_row` 成功录入某个字段
- **THEN** 步骤结果 SHALL 保留原有 `column` 和 `value`
- **AND** 步骤结果 SHALL 包含该字段的目标列身份信息，例如 `fieldid`、`data_field`、`table_fieldid` 或等价诊断字段

#### Scenario: 身份冲突时失败而不是报告成功
- **WHEN** 运行时定位结果能判断实际命中的单元格身份与目标列身份冲突
- **THEN** 系统 MUST 让当前 `editable_table.fill_row` 步骤失败
- **AND** 错误信息 MUST 包含 DSL 列名、目标列身份、实际命中身份或定位来源
