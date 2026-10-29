## MODIFIED Requirements

### Requirement: 步骤执行前解析运行期变量
系统 SHALL 在每个组件步骤执行前递归解析完整 `target` 中的运行期变量，并在变量未写入时阻止业务交互。

#### Scenario: 引用尚未捕获的变量
- **WHEN** 某个组件步骤的 `target` 使用 `{{yjxm.project_code}}`
- **AND** 当前 suite 运行期变量上下文尚未写入 `yjxm.project_code`
- **THEN** executor MUST 在点击、录入、查询、树选择或表格选择之前失败
- **AND** 错误信息 MUST 包含未定义变量名 `yjxm.project_code`

#### Scenario: random token 保持既有运行期行为
- **WHEN** 多个组件步骤的 `target` 使用同一个 `{{random.suffix}}`
- **THEN** executor MUST 在每个组件执行方法读取目标前完成解析
- **AND** executor MUST 为这些步骤复用同一个缓存随机值
- **AND** suite 捕获变量上下文 MUST NOT 覆盖 `random.*` 的解析逻辑

#### Scenario: 树单节点标签使用运行期变量
- **WHEN** `tree.select` 的 `target.label` 使用 `{{random.suffix}}`
- **THEN** executor MUST 将解析后的实际值传给树运行时
- **AND** executor MUST NOT 把占位符字面量作为树搜索或节点匹配文本

#### Scenario: 树多节点标签使用运行期变量
- **WHEN** `tree.select` 的 `target.labels` 或 `target.values` 包含运行期变量
- **THEN** executor MUST 在逐个选择节点前解析每个列表项
- **AND** 每个树运行时调用 MUST 接收对应的解析后实际值

#### Scenario: 捕获变量支持字符串拼接
- **WHEN** 某个组件步骤的字符串值为 `项目-{{project.code}}`
- **AND** 当前 suite 运行期变量上下文中 `project.code` 的值为 `3600001`
- **THEN** executor MUST 将该字符串解析为 `项目-3600001`
