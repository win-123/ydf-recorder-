## ADDED Requirements

### Requirement: 表格单元格链接消费统一表格作用域
系统 MUST 在执行 `table.click_cell_link` 前将链接列和全部行匹配列作为必需列解析到唯一表格作用域，并只在该作用域内定位目标业务行和链接。

#### Scenario: 链接列属于另一表格时在点击前失败
- **WHEN** `target.table` 指向一张表格
- **AND** `target.column` 只存在于另一张表格
- **THEN** 步骤 MUST 在行查找和链接点击前失败
- **AND** 系统 MUST NOT 改选包含链接列的其它表格

#### Scenario: 链接动作使用当次作用域证据
- **WHEN** 表格作用域成功解析且目标链接被点击
- **THEN** 步骤数据 MUST 包含实际表格 fieldid、链接列和匹配列证据
