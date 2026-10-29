## ADDED Requirements

### Requirement: Form assert values reads checkbox state
系统 SHALL 允许 `form.assert_values` 对普通表单 checkbox 字段读取并断言勾选状态。

#### Scenario: 断言已勾选的 YDFCheckbox
- **WHEN** 用例执行 `form.assert_values`，目标字段模板组件为 `YDFCheckbox`，且期望值为 `on`
- **THEN** 运行时 MUST 从该字段的 checkbox 控件、wrapper、`aria-checked` 或 checked class 读取真实勾选状态
- **AND** 当该字段已勾选时，步骤 MUST 成功
- **AND** 步骤结果中该字段的 `actual` MUST 为 `on`

#### Scenario: 断言未勾选的 YDFCheckbox
- **WHEN** 用例执行 `form.assert_values`，目标字段模板组件为 `YDFCheckbox`，且期望值为 `off`
- **THEN** 运行时 MUST 从该字段的 checkbox 状态来源读取真实未勾选状态
- **AND** 当该字段未勾选时，步骤 MUST 成功
- **AND** 步骤结果中该字段的 `actual` MUST 为 `off`

#### Scenario: Checkbox 期望值支持等价语义
- **WHEN** 用例执行 `form.assert_values` 断言普通表单 checkbox 字段
- **THEN** 系统 MUST 将 `on`、`true`、`1`、`yes`、`是`、`勾选`、`已勾选`、`选中` 和 `checked` 识别为已勾选期望
- **AND** 系统 MUST 将 `off`、`false`、`0`、`no`、`否`、`未勾选`、`不勾选`、`未选中` 和 `unchecked` 识别为未勾选期望

### Requirement: Checkbox value reading avoids unrelated text fallback
系统 MUST 在字段被识别为普通表单 checkbox 时使用 checkbox 状态语义读取，不得把邻近表格、字段标签或容器文本作为字段值。

#### Scenario: 不读取邻近表格表头
- **WHEN** checkbox 字段附近存在表格，且表格表头包含 `序号` 等文本
- **THEN** `form.assert_values` MUST NOT 将表格表头文本作为 checkbox 字段的实际值
- **AND** 如果无法读取 checkbox 状态，步骤 MUST 失败并给出 checkbox 状态不可读的错误，而不是返回表格文本

#### Scenario: 不把 Checkbox 默认 value 当作状态
- **WHEN** checkbox DOM 中存在 `input[type=checkbox]`，且该 input 的 `value` 为浏览器默认值 `on`
- **THEN** 系统 MUST 使用 `checked`、`aria-checked` 或 checked class 判断状态
- **AND** 系统 MUST NOT 仅因 `input.value` 为 `on` 就判定该字段已勾选

### Requirement: Same-name checkbox fields resolve current tab
系统 SHALL 在多个同名表单 checkbox 字段同时存在时，将 `form.assert_values` 解析到当前活动页签或当前可交互区域内的字段。

#### Scenario: 当前页签断言命中支出计划信息字段
- **WHEN** 用例先执行 `tab.click` 切换到 `支出计划信息`，随后执行 `form.assert_values` 断言 `隐藏0金额行`
- **THEN** executor MUST 优先选择当前页签内容区内的 `隐藏0金额行` 字段
- **AND** 步骤结果中的 `fieldid` MUST 对应该页签下的 checkbox 字段身份，例如 `hideZero`

#### Scenario: 当前页签断言命中项目预算信息字段
- **WHEN** 用例先执行 `tab.click` 切换到 `项目预算信息`，随后执行 `form.assert_values` 断言 `隐藏0金额行`
- **THEN** executor MUST 优先选择当前页签内容区内的 `隐藏0金额行` 字段
- **AND** 步骤结果中的 `fieldid` MUST 对应该页签下的 checkbox 字段身份，例如 `hideZeroBgt`

#### Scenario: 同名同 property_uri 不按模板顺序误选
- **WHEN** 两个 checkbox 字段中文名、`dataField` 和 `property_uri` 都相同，但位于不同页签
- **THEN** 系统 MUST NOT 仅按模板顺序或 `property_uri` 返回第一个候选
- **AND** 系统 MUST 使用当前运行时可见性、活动页签上下文和可读状态控件来消除歧义

### Requirement: Checkbox assertions remain scoped to form fields
系统 MUST 将普通表单 checkbox 断言与表格行选择、表头全选和树节点选择区分开。

#### Scenario: 表格选择 Checkbox 不作为表单字段断言目标
- **WHEN** 页面表格数据行或表头存在 checkbox，且用例执行 `form.assert_values`
- **THEN** 系统 MUST NOT 将表格行选择 checkbox 或表头全选 checkbox 绑定为普通表单字段
- **AND** 表格选择行为 MUST 继续由 `table_row_selection.select` 及其专用能力处理

#### Scenario: 树节点 Checkbox 不作为表单字段断言目标
- **WHEN** 页面树控件节点前存在 checkbox，且用例执行 `form.assert_values`
- **THEN** 系统 MUST NOT 将树节点 checkbox 绑定为普通表单字段
- **AND** 树节点选择行为 MUST 继续由 `tree.select` 及其专用能力处理
