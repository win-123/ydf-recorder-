## ADDED Requirements

### Requirement: 可编辑表格新增复用已解析作用域令牌
系统在 `editable_table.add_row` 执行前已经解析出唯一 `ResolvedTableScope` 时，新增入口点击前后的行状态验证 MUST 优先复用该作用域令牌定位目标根。背景列表、相邻明细表和包含多个表格的外层页面容器 MUST NOT 覆盖有效作用域令牌对应的目标根。

#### Scenario: 有效作用域令牌限定新增行验证
- **WHEN** `editable_table.add_row` 已解析出目标表格作用域令牌
- **AND** 页面同时存在背景列表与目标可编辑表格
- **THEN** 运行时 MUST 在令牌对应根内采集点击前后的真实数据行
- **AND** 步骤报告中的验证根来源 SHALL 表明复用了已解析表格作用域

#### Scenario: 目标表格从一行增长到两行
- **WHEN** 页面业务联动已经在目标表格生成第 1 行
- **AND** DSL 明确执行一次 `editable_table.add_row`
- **THEN** 运行时 MUST 点击目标表格新增入口一次
- **AND** 步骤报告 MUST 记录目标表格真实数据行从 1 行增长到 2 行
- **AND** 系统 MUST NOT 将背景列表行数作为新增成功证据

#### Scenario: 作用域令牌失效时保持失败关闭
- **WHEN** 已解析作用域令牌在新增验证时不再对应唯一可见目标根
- **THEN** 当前步骤 MUST 在点击新增入口前失败
- **AND** 运行时 MUST NOT 按全页身份或行数重新猜测目标根
