## ADDED Requirements

### Requirement: 可编辑表格动作消费统一表格作用域
系统 MUST 在执行 `editable_table.add_row` 或 `editable_table.fill_row` 前解析唯一的当前前景可编辑表格作用域。`fill_row` 的全部字段列 MUST 在激活行或单元格前完成预校验；`add_row` SHALL 使用目标表格身份和可见列证据限定新增入口与新增结果验证。

#### Scenario: fill_row 缺少任一字段列时不开始录入
- **WHEN** `editable_table.fill_row` 声明多个字段
- **AND** 已解析目标表格缺少任一字段列或父表头限定无法唯一匹配
- **THEN** 当前步骤 MUST 在激活目标行或首个单元格前失败
- **AND** 系统 MUST NOT 部分录入其它字段

#### Scenario: add_row 只验证目标作用域
- **WHEN** `editable_table.add_row` 已解析当前前景目标表格
- **THEN** 新增入口扫描和行增长验证 MUST 限定到该作用域
- **AND** 背景表格或相邻表格的行变化 MUST NOT 作为新增成功证据

#### Scenario: DOM 根失效时由统一能力受控重试
- **WHEN** 可编辑表格作用域解析后、点击新增入口或激活单元格前发现 DOM 根失效
- **THEN** 系统 SHALL 在未产生页面副作用时重新解析一次
- **AND** 动作 implementation MUST NOT 使用原始表名自行扫描其它表格
