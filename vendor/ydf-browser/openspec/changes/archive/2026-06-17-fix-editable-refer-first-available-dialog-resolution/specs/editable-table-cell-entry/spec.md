## ADDED Requirements

### Requirement: 可编辑表格参照列必须解析当前字段候选层
系统 MUST 在 `editable_table.fill_row` 录入可编辑表格弹出参照列时，只能在当前字段触发或当前有效候选参照层内执行过滤、`first_available`、`match` 或确认操作。

#### Scenario: 收款方户名 first_available 不使用主页面文本
- **WHEN** DSL 文档执行 `editable_table.fill_row`，目标表格为 `汇款转账`
- **AND** 字段 `收款方户名` 的模板列组件为 `YDFReferSelect` 或等价 `dataType=refer`
- **AND** 字段值包含 `filter: 严巴天` 和 `first_available: true`
- **AND** 当前页面背景区域包含 `关联单据`、`借款信息`、`借款单号`、`本次核销金额` 或其他非候选参照文本
- **THEN** 运行时 MUST 点击 `收款方户名` 单元格自身的参照触发控件并解析该字段打开的候选参照根
- **AND** 运行时 MUST NOT 将背景页面、当前编辑页内容卡片、业务助手或已关闭旧弹层作为 `收款方户名` 的候选参照根
- **AND** 运行时 MUST NOT 在这些背景文本中查找 `严巴天` 或第一条可用候选

#### Scenario: 未打开当前字段候选层时在当前字段失败
- **WHEN** `editable_table.fill_row` 的目标字段值包含 `first_available`、`match`、`row_number`、`selections` 或其他结构化弹出参照语义
- **AND** 运行时点击目标单元格后无法打开或解析当前字段的有效候选参照根
- **THEN** 当前 `editable_table.fill_row` 步骤 MUST 在该字段失败
- **AND** 错误信息 MUST 包含表格名、行号、列名、字段组件、结构化目标摘要和可见页面或前景层诊断
- **AND** 错误信息 MUST 指向参照候选层未打开或未解析，而不是报告在背景页面中未找到候选值

#### Scenario: 成功选择后报告当前候选层诊断
- **WHEN** `editable_table.fill_row` 成功录入可编辑表格弹出参照列
- **AND** 字段值包含 `filter` 和 `first_available`
- **THEN** 字段级结果 SHALL 保留列身份和定位来源诊断
- **AND** 字段级结果 SHALL 包含实际选择候选的诊断，至少能判断候选来源不是背景页面文本
- **AND** 如果参照候选层自动关闭且目标单元格已回填，系统 MUST 按既有自动关闭回填规则判定该字段成功

### Requirement: 可编辑表格结构化参照修复不得回退既有树表能力
系统 MUST 保持可编辑表格结构化弹出参照目标的既有能力，包括 `tree + first_available`、`tree + match`、`match.contains`、`row_number` 和 `selections`。

#### Scenario: 树表 first_available 仍选择右侧候选行
- **WHEN** 可编辑表格字段值包含 `tree` 和 `first_available: true`
- **AND** 当前有效候选参照根包含左树和右侧候选表格
- **THEN** 运行时 MUST 先应用树上下文
- **AND** 运行时 MUST 继续优先选择右侧候选表格中的第一条有效数据行
- **AND** 运行时 MUST NOT 为修复普通 `YDFReferSelect` 回归而退回点击左树节点、普通文本节点或把对象字符串化写入单元格

#### Scenario: 树表 match 与 contains 保持兼容
- **WHEN** 可编辑表格字段值包含 `tree` 和 `match.column`
- **AND** `match` 使用 `equals` 或 `contains`
- **THEN** 运行时 MUST 继续在当前有效候选参照根内按右侧候选表格匹配目标行
- **AND** 运行时 MUST 保持 W table、分离表头表体、候选行选择态和确认回填的既有语义

