# attachment-upload Specification

## Purpose
定义 YonDiF 附件组件 `attachment.upload` 的上传入口定位、业务完成等待、失败诊断和报告证据要求，确保 DSL 步骤只在目标附件被页面业务侧接受后继续执行。
## Requirements
### Requirement: 附件上传等待业务接受状态
`attachment.upload` SHALL 等待目标 YonDiF 附件组件显示上传文件已被业务页面接受后，执行器才能继续执行下一条 DSL 步骤。

#### Scenario: 上传在保存前等待
- **WHEN** DSL 用例通过 `component: attachment` 上传文件，并且 YonDiF 页面在 `set_input_files` 后异步创建附件行
- **THEN** `attachment.upload` MUST 保持执行中，直到目标附件组件暴露完成状态，例如上传文件名、附件行、更新后的附件数量，或等价的业务可见接受状态
- **AND** 当目标附件组件仍显示为空时，下一步 MUST NOT 执行

#### Scenario: 已接受的上传返回证据
- **WHEN** `attachment.upload` 成功完成
- **THEN** 步骤结果 MUST 包含已上传文件路径，并 SHOULD 包含可诊断证据，例如目标附件标签或 fieldid、等待耗时，以及用于确认完成的信号

### Requirement: 附件上传限定在目标组件范围内
`attachment.upload` SHALL 在目标附件组件范围内解析和验证上传结果，不能把无关页面文本或全局上传控件作为完成证据。

#### Scenario: 保持目标组件范围
- **WHEN** 当前页面存在模板上传组件，例如 `LCDUploadNext`，且其 label 或 fieldid 与 DSL 附件类型匹配
- **THEN** 运行时 MUST 在该组件范围内定位文件输入框并验证上传完成
- **AND** 组件外部的文本或控件 MUST NOT 单独满足上传完成检查

#### Scenario: 兜底范围保持受限
- **WHEN** 模板元数据不可用或不完整
- **THEN** 运行时 MAY 使用可见 DOM 兜底匹配
- **AND** 兜底匹配 MUST 限定在同时包含目标附件标签和文件输入框的可见上传区域内

### Requirement: 附件无效或未完成时上传失败
当选择的文件不能被目标附件组件接受时，`attachment.upload` MUST 在上传步骤失败。

#### Scenario: 保存前拒绝不匹配的文件类型
- **WHEN** 目标附件组件声明了允许的文件类型列表，且 DSL 文件扩展名不在允许范围内
- **THEN** `attachment.upload` MUST 以明确的文件类型不匹配错误失败
- **AND** 执行器 MUST NOT 继续执行后续保存或确认步骤

#### Scenario: 上传完成等待超时
- **WHEN** 文件已被选择，但目标附件组件在超时前没有暴露已接受附件的状态
- **THEN** `attachment.upload` MUST 以超时错误失败
- **AND** 失败诊断 MUST 包含目标附件上下文，并在可用时包含截图

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
