## MODIFIED Requirements

### Requirement: 成功和失败业务断言必须生成结构化回执

系统 MUST 复用现有业务断言分类，为成功和不符合预期的断言记录 expected/actual、业务目标与作用域、匹配业务行和候选请求引用，且 MUST NOT 把回执本身解释为被测业务变更已验证。

#### Scenario: 识别现有业务断言

- **WHEN** 步骤为 `form.assert_values`、`notification.assert`、`workflow_result.assert`、`table.assert_column_values`、`table.assert_columns`、`table.assert_empty` 或 `table.assert_row_values`
- **THEN** 系统 MUST 生成业务断言回执
- **AND** `import.upload target.assert` MUST 继续只表示导入动作状态，不得替代后置业务断言

#### Scenario: 成功断言不生成高成本页面包

- **WHEN** 业务断言成功
- **THEN** 回执 MUST 记录断言 action、目标作用域、expected/actual、适用的查询完成信号、匹配行身份和相关列
- **AND** 系统 MUST NOT 因成功回执额外生成截图或 DOM 包

#### Scenario: 选择候选请求范围

- **WHEN** 系统为断言回执列出候选 `request_id`
- **THEN** 范围 MUST 从当前断言之前最近一个非断言 DSL 步骤开始，到当前断言完成为止
- **AND** 不存在前置非断言步骤时 MUST 从用例开始
- **AND** 连续断言 MUST 共用最近非断言步骤的起点
- **AND** 工具 MUST NOT 根据 URL 或响应内容自动选择最相关请求

#### Scenario: DSL 通过但绿色证据不足

- **WHEN** DSL 步骤全部成功，但 skill 无法找到相关完整 API 响应或证明相关请求命中本地转发
- **THEN** 运行事实只能称为执行成功
- **AND** skill MUST 使用 `blocked/evidence_unavailable` 表达变更尚未验证

#### Scenario: 工作流批量结果层回执保留结果证据

- **WHEN** 步骤为 `workflow_result.assert`
- **THEN** 回执 MUST 记录结果层作用域、声明的统计 expected 和实际 `counts`
- **AND** `data.workflow_result` MUST 保留结果层语义和可用证据

#### Scenario: 保持导入状态断言边界

- **WHEN** 步骤为 `import.upload target.assert`
- **THEN** 系统 MUST 继续只表示导入动作状态
- **AND** 该步骤 MUST NOT 替代后置业务断言
