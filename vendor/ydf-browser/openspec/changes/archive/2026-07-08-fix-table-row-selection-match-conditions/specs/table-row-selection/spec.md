## ADDED Requirements

### Requirement: 复合条件行选择必须完整匹配同一业务行
系统 SHALL 在 `table_row_selection.select` 使用 `target.match.conditions` 时，将每个条件绑定到其声明列，并只选择同一业务行内满足全部条件的行。

#### Scenario: 首条件重复时选择完整匹配行
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.table` 为 `table1`
- **AND** `target.match.conditions` 包含 `一级项目名称=财政一级项目ys06231632` 和 `指标金额=888.00`
- **AND** 第一条可见数据行只满足 `一级项目名称=财政一级项目ys06231632`
- **AND** 第四条可见数据行同时满足 `一级项目名称=财政一级项目ys06231632` 和 `指标金额=888.00`
- **THEN** runtime MUST 点击第四条业务行的行选择 checkbox 或等效行选择控件
- **AND** runtime MUST NOT 选择第一条只满足部分条件的业务行

#### Scenario: 复合条件按声明列匹配而非整行包含
- **WHEN** `target.match.conditions` 包含多个列条件
- **AND** 某条数据行的整行文本包含所有条件值，但至少一个条件值位于错误列
- **THEN** runtime MUST NOT 将该行视为完整匹配行
- **AND** runtime MUST 继续查找每个条件值都位于声明列中的业务行

#### Scenario: 复合条件顺序不影响选择结果
- **WHEN** 两次 `table_row_selection.select` 使用相同的 `target.match.conditions` 集合但条件顺序不同
- **AND** 当前表格中存在唯一完整匹配业务行
- **THEN** runtime MUST 在两次执行中选择同一业务行
