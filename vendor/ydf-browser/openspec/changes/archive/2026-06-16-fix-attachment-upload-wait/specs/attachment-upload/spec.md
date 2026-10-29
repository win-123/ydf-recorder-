## ADDED Requirements

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
