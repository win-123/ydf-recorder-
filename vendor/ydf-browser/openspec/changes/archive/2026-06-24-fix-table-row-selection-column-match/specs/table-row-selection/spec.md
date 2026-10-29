## ADDED Requirements

### Requirement: 按列值选择表格行
系统 SHALL 在 `table_row_selection.select` 使用 `target.match.column` 和 `target.match.equals` 时，按指定表格列的单元格值定位业务行，并在该行上执行行选择。

#### Scenario: 文本布尔列值可定位业务行
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.match.column` 为 `政府采购标识`
- **AND** `target.match.equals` 为 `是`
- **AND** 目标表格中存在一行的 `政府采购标识` 单元格显示文本为 `是`
- **THEN** runtime MUST 将该单元格值作为匹配依据定位业务行
- **AND** runtime MUST 点击同一业务行的行选择 checkbox 或等效行选择控件
- **AND** runtime MUST NOT 将 `政府采购标识` 这一文本单元格本身当作 checkbox

#### Scenario: 单值匹配不得退化为整行文本误选
- **WHEN** `table_row_selection.select` 的 `target.match.column` 为 `政府采购标识`
- **AND** `target.match.equals` 为 `是`
- **AND** 第一条可见数据行整行文本包含 `是`，但其 `政府采购标识` 单元格不是 `是`
- **THEN** runtime MUST NOT 选择该行
- **THEN** runtime MUST 继续查找 `政府采购标识` 单元格等于 `是` 的数据行

### Requirement: 表格行选择的列归属作用域
系统 SHALL 在 `table_row_selection.select` 未显式指定 `target.table` 时，使用目标匹配列的表格归属限定选择作用域；无法唯一确定时必须在点击前失败。

#### Scenario: 目标列唯一归属于可用指标表
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** 未填写 `target.table`
- **AND** `target.match.column` 为 `政府采购标识`
- **AND** 当前模板中只有 `可用指标` 表包含 `政府采购标识` 列
- **THEN** executor MUST 将 `可用指标` 解析为本次行选择作用域
- **AND** executor MUST 在可用时向 runtime 传递该表的 `table_fieldid` 和列清单

#### Scenario: 多张表都包含目标列时拒绝歧义
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** 未填写 `target.table`
- **AND** 当前模板中多张可见主表都包含 `target.match.column`
- **THEN** 步骤 MUST 在点击任何行选择控件前失败
- **THEN** 错误信息 MUST 要求补充 `target.table`

#### Scenario: 目标行存在但选择控件缺失时诊断清晰
- **WHEN** runtime 已按 `target.match.column` 和 `target.match.equals` 找到目标业务行
- **AND** 该行没有可点击的行选择 checkbox 或等效行选择控件
- **THEN** 步骤 MUST 失败
- **THEN** 错误信息 MUST 包含目标表格、目标列、匹配值，并说明未找到行选择控件
