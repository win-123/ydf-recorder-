## MODIFIED Requirements

### Requirement: 按列值选择表格行
系统 SHALL 在 `table_row_selection.select` 使用 `target.match.column` 和 `target.match.equals` 时，按指定表格列的单元格值定位业务行，并在该行上执行行选择。

#### Scenario: 文本布尔列值可定位业务行
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.match.column` 为 `政府采购标识`
- **AND** `target.match.equals` 为 `是`
- **AND** 目标表格中存在一行的 `政府采购标识` 单元格显示文本为 `是`
- **THEN** runtime MUST 将该单元格值作为匹配依据定位业务行
- **AND** runtime MUST 点击同一业务行的行选择 checkbox、等效行选择控件，或在无选择控件时点击该业务行触发表格原生选中/高亮
- **AND** runtime MUST NOT 将 `政府采购标识` 这一文本单元格本身当作 checkbox

#### Scenario: 单值匹配不得退化为整行文本误选
- **WHEN** `table_row_selection.select` 的 `target.match.column` 为 `政府采购标识`
- **AND** `target.match.equals` 为 `是`
- **AND** 第一条可见数据行整行文本包含 `是`，但其 `政府采购标识` 单元格不是 `是`
- **THEN** runtime MUST NOT 选择该行
- **THEN** runtime MUST 继续查找 `政府采购标识` 单元格等于 `是` 的数据行

#### Scenario: 目标行存在但选择控件缺失时点击业务行
- **WHEN** runtime 已按 `target.match.column` 和 `target.match.equals` 找到目标业务行
- **AND** 该行没有可点击的行选择 checkbox 或等效行选择控件
- **AND** 该行位于已解析的目标表格作用域内
- **THEN** runtime MUST 点击该目标业务行以触发表格原生选中/高亮
- **AND** runtime MUST NOT 退回全页面裸文本点击
