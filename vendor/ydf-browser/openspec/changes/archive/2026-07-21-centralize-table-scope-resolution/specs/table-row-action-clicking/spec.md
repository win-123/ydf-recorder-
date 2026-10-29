## MODIFIED Requirements

### Requirement: 未指定表格的行按钮保持兼容
系统 SHALL 在未指定 `target.table` 时，仅当统一表格作用域能力能根据当前前景表格和动作引用列解析出唯一表格时继续执行 `table_row_action.click`。目标行在全页面唯一 MUST NOT 作为跨多个表格消歧的依据。

#### Scenario: 既有主表行按钮继续可用
- **WHEN** DSL 文档执行 `table_row_action.click`
- **AND** 未填写 `target.table`
- **AND** 前序步骤没有可消费的可编辑表格作用域
- **AND** `target.row_number` 为 `1`
- **AND** 当前前景只有一张可操作主表，目标行 hover 后存在目标行级按钮
- **THEN** 系统 MUST 将唯一主表解析为表格作用域
- **AND** runtime MUST 在该作用域内点击目标行级按钮

#### Scenario: 多表格时不按目标行唯一猜测
- **WHEN** DSL 文档执行 `table_row_action.click`
- **AND** 未填写 `target.table`
- **AND** 当前前景存在多张可操作表格
- **AND** 只有一张表格包含目标行文本
- **THEN** 步骤 MUST 在行查找前失败
- **AND** 错误信息 MUST 要求提供可唯一解析的表格身份或列语义

#### Scenario: 显式表格失败时不回退全页面行
- **WHEN** DSL 文档执行 `table_row_action.click`
- **AND** `target.table` 为 `物资信息`
- **AND** 运行时无法在 `物资信息` 表格作用域内找到目标业务行
- **THEN** 步骤 MUST 失败
- **AND** runtime MUST NOT 回退到全页面第 N 行或其它表格中的同名行
