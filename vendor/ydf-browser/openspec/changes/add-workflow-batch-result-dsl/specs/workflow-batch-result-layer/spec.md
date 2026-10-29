## Purpose

为 YonDiF 工作流批量操作提供可声明、可验证的结果层观察能力，使批量统计、失败明细和分层关闭动作能够进入结构化报告，而不会被误当作普通弹窗或普通页面提示。

## ADDED Requirements

### Requirement: 工作流批量结果层语义识别

系统 MUST 只在运行时同时观察到可见的工作流结果语义、可解析的批量统计和结果层操作入口时，将当前前景层识别为工作流批量结果层。系统 MUST NOT 仅凭 `.error-content` 或其他单一 CSS 类名完成识别。

#### Scenario: 识别可交互的工作流批量结果层

- **WHEN** 当前页面出现可见结果层
- **AND** 结果层包含工作流批量完成或部分失败语义
- **AND** 结果层包含可解析的总数、成功数和失败数
- **AND** 结果层包含“确认”或“查看详情”入口
- **THEN** runtime MUST 将该前景层识别为工作流批量结果层
- **AND** 后续 `workflow_result` 步骤 MUST 读取同一结果层

#### Scenario: 避免把同名错误容器识别为结果层

- **WHEN** 页面存在 `.error-content` 类名的上传错误或其他非工作流容器
- **AND** 该容器缺少工作流结果语义、批量统计或结果层操作入口中的任一必要条件
- **THEN** runtime MUST NOT 将该容器识别为工作流批量结果层

### Requirement: 结构化结果层断言

系统 SHALL 支持 `workflow_result.assert`。其 target MUST 至少包含一个整数目标字段 `total`、`succeeded` 或 `failed`；提供多个字段时 MUST 对所有字段执行精确匹配。标题或提示文案约束为可选辅助条件，不得替代结构化统计字段。

#### Scenario: 结果层统计与预期一致

- **WHEN** DSL 执行 `workflow_result.assert`
- **AND** 当前工作流批量结果层的统计值满足 target 中声明的 `total`、`succeeded` 和 `failed`
- **THEN** 步骤 MUST 成功
- **AND** 步骤数据 MUST 在 `data.workflow_result` 中记录可见语义和实际 `counts`
- **AND** 步骤 MUST 生成现有格式的业务断言回执，包含 expected 和 actual

#### Scenario: 结果层统计与预期不一致

- **WHEN** DSL 执行 `workflow_result.assert`
- **AND** 结果层已被成功识别
- **AND** 至少一个声明的统计字段与实际值不一致
- **THEN** 步骤 MUST 以 `业务断言不符合` 失败
- **AND** 失败结果 MUST 保留实际 `counts`、结果层语义和可用页面证据
- **AND** 当前用例 MUST 沿用现有断言失败语义停止后续步骤

#### Scenario: 结果层不可观察或统计不可解析

- **WHEN** DSL 执行 `workflow_result.assert`
- **AND** 在现有步骤超时窗口内没有识别到结果层，或统计字段无法可靠解析
- **THEN** 步骤 MUST 失败
- **AND** 报告 MUST 将原因分类为 `target_unavailable` 或 `evidence_unavailable`
- **AND** 报告 MUST 包含实际页面语义和诊断证据（如可用）

### Requirement: 未声明结果层保护

系统 MUST 防止真实出现的工作流批量结果层被 DSL 静默忽略。

#### Scenario: 点击动作后未声明结果层步骤

- **WHEN** 一个点击类动作完成后真实出现工作流批量结果层
- **AND** DSL 的下一步不是 `workflow_result.assert`
- **THEN** 运行 MUST 进入验证阻断
- **AND** 报告 MUST 说明存在未处理的工作流批量结果层
- **AND** 报告 MUST 保留结果层统计和页面证据

#### Scenario: 详情或关闭操作不能越过结果层断言

- **WHEN** DSL 直接执行 `workflow_result.details` 或 `workflow_result.confirm`
- **AND** 当前结果层尚未由同一用例中的 `workflow_result.assert` 成功观察
- **THEN** 步骤 MUST 失败
- **AND** 报告 MUST 说明结果层尚未完成断言前置条件

### Requirement: 全部成功路径保持页面提示语义

系统 MUST 保持全部成功批量操作使用 `notification.assert` 的现有语义，不得为不存在的工作流批量结果层生成虚假结果。

#### Scenario: 批量操作全部成功

- **WHEN** 批量工作流操作完成且页面只显示 `成功N条` 页面提示
- **AND** 页面未创建工作流批量结果层
- **THEN** `notification.assert` MUST 能够断言该成功提示
- **AND** `workflow_result.assert` MUST NOT 被隐式执行或伪造成功结果层

### Requirement: 失败详情采集

系统 SHALL 支持 `workflow_result.details`，且该操作 MUST 在同一结果层已经通过 `workflow_result.assert` 后执行。该操作 MUST 打开内层失败详情弹窗，并将可见失败明细写入 `data.workflow_result.details`；第一版不提供详情行级 DSL 断言。

#### Scenario: 打开并采集失败详情

- **WHEN** `workflow_result.assert` 已成功观察结果层
- **AND** DSL 执行 `workflow_result.details`
- **THEN** runtime MUST 点击“查看详情”入口
- **AND** runtime MUST 等待内层详情弹窗和可见明细稳定
- **AND** 步骤数据 MUST 记录至少可见的单据编码、错误原因和错误码字段（如页面提供）
- **AND** 外层工作流批量结果层 MUST 保持可识别状态

#### Scenario: 详情弹窗或明细不可采集

- **WHEN** “查看详情”入口可点击
- **AND** 内层详情弹窗或其可见明细在步骤超时窗口内无法确认
- **THEN** `workflow_result.details` MUST 失败
- **AND** 报告 MUST 说明详情证据不可用并保留可用诊断

### Requirement: 分层关闭语义

系统 SHALL 支持 `workflow_result.confirm` 关闭外层结果层，并 MUST 验证外层结果层实际消失。内层详情弹窗仍由既有 `dialog.confirm` 关闭。

#### Scenario: 先关闭详情再关闭外层结果层

- **WHEN** `workflow_result.details` 已打开内层详情弹窗
- **AND** DSL 使用 `dialog.confirm` 关闭内层按钮“确定”
- **AND** 随后执行 `workflow_result.confirm`
- **THEN** `dialog.confirm` MUST 只作用于内层详情弹窗
- **AND** `workflow_result.confirm` MUST 点击外层“确认”入口
- **AND** 步骤 MUST 等待并确认外层结果层不再可见

#### Scenario: 外层结果层关闭失败

- **WHEN** `workflow_result.confirm` 已触发点击
- **AND** 外层结果层在步骤超时窗口结束后仍可见
- **THEN** 步骤 MUST 失败
- **AND** 报告 MUST 包含结果层仍可见的实际证据

### Requirement: 结果层报告和能力声明

系统 MUST 在结果层相关步骤中提供稳定的结构化报告数据，并声明该 DSL 能力。

#### Scenario: 结果层步骤写入结构化报告

- **WHEN** 任一 `workflow_result.assert`、`workflow_result.details` 或 `workflow_result.confirm` 步骤完成或失败
- **THEN** 步骤数据 MUST 使用 `data.workflow_result`
- **AND** 该对象 MUST 按可用性记录可见语义、`counts`、`details` 和操作状态
- **AND** 断言步骤 MUST 继续使用现有业务断言回执

#### Scenario: 能力可发现但只在实际使用时启用

- **WHEN** 工具执行 `doctor` 或兼容性预检
- **THEN** `capabilities.available` MUST 声明 `workflow_result`
- **WHEN** 本次运行实际执行任一 `workflow_result` 步骤
- **THEN** `capabilities.enabled` MUST 包含 `workflow_result`
- **AND** 工具 MUST NOT 要求额外运行开关
