# table-cell-link-clicking Specification

## Purpose
约束表格单元格链接按唯一表格作用域、目标列和业务行定位后点击。系统在产生页面副作用前校验链接列和行匹配列，并在目标表格、业务行或链接不存在时明确失败，不改选其它表格中的同名链接。
## Requirements
### Requirement: 表格单元格链接点击 DSL
系统 SHALL 支持 `table.click_cell_link` 组件操作，用于声明在目标表格行的指定列中点击超链接。

#### Scenario: 接受按匹配行点击列链接
- **WHEN** DSL 文档包含 `component: table`、`operation: click_cell_link`
- **AND** `target.match.column` 为 `序号`
- **AND** `target.match.equals` 为 `1`
- **AND** `target.column` 为 `任务编码`
- **THEN** DSL validation MUST 接受该步骤
- **AND** `target.column` MUST 被解释为待点击链接所在的页面列名

#### Scenario: 接受按行号点击列链接
- **WHEN** DSL 文档包含 `table.click_cell_link`
- **AND** `target.row_number` 为 `1`
- **AND** `target.column` 为 `任务编码`
- **THEN** DSL validation MUST 接受该步骤

#### Scenario: 缺少目标列时失败
- **WHEN** DSL 文档包含 `table.click_cell_link`
- **AND** 未填写 `target.column`
- **THEN** DSL validation MUST 在业务步骤执行前失败
- **AND** 错误信息 MUST 说明缺少 `target.column`

#### Scenario: 缺少行定位时失败
- **WHEN** DSL 文档包含 `table.click_cell_link`
- **AND** 已填写 `target.column`
- **AND** 未填写 `target.match`、`target.row_number`、`target.row_index`、`target.first_available` 或 `target.select_first_available`
- **THEN** DSL validation MUST 在业务步骤执行前失败
- **AND** 错误信息 MUST 说明缺少行定位属性

### Requirement: 表格单元格链接定位
系统 SHALL 复用现有表格作用域、行定位和列身份规则，在目标表格内定位目标业务行和目标列单元格后再点击链接。

#### Scenario: 点击 link 组件列中的任务编码
- **WHEN** 测试集执行 `table.click_cell_link`
- **AND** 当前页面为 `盘点任务填报`
- **AND** `target.match.column` 为 `序号`、`target.match.equals` 为 `1`
- **AND** `target.column` 为 `任务编码`
- **AND** 模板中 `任务编码` 表格列的组件名为 `link`
- **THEN** executor MUST 将 `任务编码` 解析为目标表格列
- **AND** runtime MUST 在目标行的 `任务编码` 单元格内点击真实可点击链接
- **AND** runtime MUST NOT 点击页面顶部工具栏或行级工具栏中的 `查看任务`

#### Scenario: 多表格页面使用 target.table 限定链接来源
- **WHEN** 当前页面存在多张可见主表格
- **AND** DSL 的 `table.click_cell_link` 填写 `target.table`
- **THEN** executor MUST 将行匹配、列定位和链接点击限定在该表格作用域内
- **AND** runtime MUST NOT 在其它表格或背景表格中点击同名列链接

#### Scenario: 目标列不可见时允许横向滚动
- **WHEN** 目标业务行存在
- **AND** `target.column` 对应列当前不在可见横向视口内
- **THEN** runtime SHALL 按现有表格列滚动策略尝试滚动到目标列
- **AND** runtime MUST 只在目标列单元格可定位后点击链接

### Requirement: 链接文本和可点击性校验
系统 SHALL 支持用 `target.link_text` 限定单元格内的具体链接文本，并在目标单元格没有真实可点击链接时失败。

#### Scenario: link_text 匹配后点击
- **WHEN** `table.click_cell_link` 的 `target.link_text` 为 `202600000000060`
- **AND** 目标单元格中存在文本为 `202600000000060` 的可点击链接
- **THEN** runtime MUST 点击该链接
- **AND** runtime MUST NOT 点击同一单元格内其它链接或整行区域

#### Scenario: 未填写 link_text 时点击单元格内唯一链接
- **WHEN** `table.click_cell_link` 未填写 `target.link_text`
- **AND** 目标单元格内只有一个可点击链接
- **THEN** runtime MUST 点击该链接

#### Scenario: 单元格不是可点击链接时失败
- **WHEN** 目标业务行和目标列单元格均存在
- **AND** 目标单元格内没有 `link` 组件证据、链接角色、按钮角色或可接收 pointer event 的链接元素
- **THEN** 当前步骤 MUST 失败
- **AND** runtime MUST NOT 退回全页面裸文本点击

### Requirement: 表格链接点击报告和后续上下文
系统 SHALL 将 `table.click_cell_link` 视为点击类动作，记录可审计步骤数据，并支持点击后的通知捕获和动态模板上下文切换。

#### Scenario: 成功点击后记录表格和列诊断
- **WHEN** `table.click_cell_link` 成功点击目标链接
- **THEN** 步骤结果 MUST 包含 `data.column`
- **AND** 步骤结果 MUST 包含目标行定位信息
- **AND** 如果 executor 解析出表格 fieldid，步骤结果 MUST 包含 `data.table_fieldid`
- **AND** 如果 runtime 记录了树形表格查找，步骤结果 MUST 包含 `data.row_search`

#### Scenario: 点击后打开动态模板
- **WHEN** `table.click_cell_link` 点击目标链接后页面打开详情页、弹窗或其它动态模板
- **THEN** executor MUST 按现有点击类动作流程等待并应用动态模板
- **AND** 后续 `form.assert_values`、`table.assert_row_values` 或 `toolbar.click` MUST 作用于新的活动模板

#### Scenario: 点击失败时保留根因诊断
- **WHEN** `table.click_cell_link` 因未找到行、未找到列或目标单元格不可点击失败
- **THEN** 错误信息 MUST 包含目标 `column`
- **AND** 错误信息 MUST 包含目标行定位信息
- **AND** 如果指定或解析出表格作用域，错误信息 MUST 包含 `table` 或 `table_fieldid`

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
