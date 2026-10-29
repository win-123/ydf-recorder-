## ADDED Requirements

### Requirement: 附件上传适配当前视图
`attachment.upload` SHALL 独立于附件管理组件当前采用附件卡片视图还是附件表格视图完成上传，且不得要求 DSL 声明视图。

#### Scenario: 附件卡片视图直接上传
- **WHEN** 目标附件组件当前显示附件卡片视图
- **THEN** 运行时 MUST 直接使用现有按附件类型展示的上传入口
- **AND** 运行时 MUST 保持附件卡片视图

#### Scenario: 附件表格视图切换后上传
- **WHEN** 目标附件组件当前显示附件表格视图
- **THEN** 运行时 MUST 在目标组件范围内切换到附件卡片视图后执行上传
- **AND** 当前视图 MUST 由可见运行时 DOM 判断，模板默认 `viewType` 只能作为诊断信息

#### Scenario: 多附件整步只切换一次
- **WHEN** 一条 `attachment.upload` 包含多个附件且初始为附件表格视图
- **THEN** 运行时 MUST 在全部附件上传前只切换一次到附件卡片视图
- **AND** 任一附件失败后 MUST 停止上传后续附件

#### Scenario: 无法切换到附件卡片视图
- **WHEN** 当前为附件表格视图但目标组件内没有可操作的附件卡片视图切换入口，或点击后视图未改变
- **THEN** `attachment.upload` MUST 失败并提供目标组件、当前视图和切换诊断
- **AND** 运行时 MUST NOT 兜底执行附件表格视图的独立上传流程

### Requirement: 附件上传恢复原视图
`attachment.upload` SHALL 在步骤结束前恢复调用时的附件视图，无论上传成功还是失败。

#### Scenario: 上传成功后恢复附件表格视图
- **WHEN** 运行时从附件表格视图切换到附件卡片视图并完成全部上传
- **THEN** 运行时 MUST 恢复附件表格视图并验证恢复结果

#### Scenario: 上传失败后恢复附件表格视图
- **WHEN** 运行时切换到附件卡片视图后发生上传失败
- **THEN** 运行时 MUST 在传播上传错误前尝试恢复附件表格视图
- **AND** 恢复错误 MUST NOT 覆盖原始上传错误

#### Scenario: 上传成功但恢复失败
- **WHEN** 全部文件已经上传成功但附件表格视图恢复失败
- **THEN** `attachment.upload` MUST 失败
- **AND** 错误和报告 MUST 明确文件已经上传且失败发生在视图恢复阶段

### Requirement: 附件上传报告视图证据
`attachment.upload` SHALL 在步骤结果中提供足以确认视图适配与恢复结果的最小证据。

#### Scenario: 返回视图证据
- **WHEN** `attachment.upload` 结束
- **THEN** 步骤结果 MUST 包含 `initial_view`、`upload_view` 和 `view_restored`
- **AND** `upload_view` MUST 为实际执行上传时的视图
