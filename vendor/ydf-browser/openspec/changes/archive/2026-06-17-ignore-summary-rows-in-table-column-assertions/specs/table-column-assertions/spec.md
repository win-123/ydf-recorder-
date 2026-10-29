## ADDED Requirements

### Requirement: 表格列值断言忽略汇总行
系统 SHALL 在执行 `table.assert_column_values` 时只采集目标表格的业务数据行，MUST 排除表格页脚、汇总、小计、合计、总计等非业务数据行。

#### Scenario: WUI 小计行不参与列值断言
- **WHEN** DSL 文档执行 `table.assert_column_values`
- **AND** `target.column` 为 `项目名称`
- **AND** 目标表格包含业务行 `项目名称 = ui自动化wdy0033`
- **AND** 目标表格末尾存在 class 包含 `tfoot-tr` 或 `bsubtotal`、行文本为 `小计 190,000.00` 的汇总行
- **THEN** runtime MUST 返回业务行中的 `ui自动化wdy0033`
- **AND** runtime MUST NOT 将汇总行中的 `190,000.00` 纳入 `values`
- **AND** 当所有业务行的 `项目名称` 均匹配 `target.equals` 时步骤 MUST 成功

#### Scenario: 中文汇总文本行不参与列值断言
- **WHEN** 目标表格存在可见行，其整行文本或首个可见单元格以 `小计`、`合计`、`汇总` 或 `总计` 开头
- **THEN** `table.assert_column_values` MUST 将该行视为汇总行并排除
- **AND** 排除逻辑 MUST 在按列 identity、列索引或几何兜底读取目标列之前生效

#### Scenario: 普通业务行仍可正常采集
- **WHEN** 目标表格存在普通业务行，其目标列值等于 `target.equals`
- **AND** 该行 class 不表示 footer、summary、total、subtotal 或 tfoot
- **AND** 该行首个可见单元格不表示 `小计`、`合计`、`汇总` 或 `总计`
- **THEN** `table.assert_column_values` MUST 保留该业务行参与断言
- **AND** 现有表格作用域、header/body 分离和固定列副本对齐能力 MUST 保持可用
