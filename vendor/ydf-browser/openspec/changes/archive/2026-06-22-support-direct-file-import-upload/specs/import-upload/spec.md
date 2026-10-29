## ADDED Requirements

### Requirement: 直连文件导入按钮
`import.upload` SHALL 支持点击后直接打开浏览器 file chooser 的 YonDiF 导入动作，而不要求这类动作必须打开平台公共导入工作台。

#### Scenario: YDFileImportButton 直连上传
- **WHEN** DSL 执行 `component: import`、`operation: upload`，并且 `target.label` 绑定到可见的 `YDFileImportButton` 或等价直连文件导入按钮
- **THEN** runtime MUST 点击该业务按钮并捕获浏览器 file chooser
- **AND** runtime MUST 将 `target.file` 或 `target.files` 指定的文件设置到该 file chooser
- **AND** runtime MUST NOT 尝试打开公共导入组件的下拉子按钮或导入工作台

#### Scenario: 公共导入保持兼容
- **WHEN** DSL 执行 `import.upload`，并且目标导入动作不是直连文件导入按钮
- **THEN** runtime MUST 保持现有公共导入组件流程
- **AND** runtime MUST 继续通过导入工作台选择文件、提交导入并等待结果

### Requirement: 导入上传报告业务结果
`import.upload` SHALL 在文件选择后报告可观察的导入业务结果，无论入口是公共导入组件还是直连文件导入按钮。

#### Scenario: 直连上传等待结果
- **WHEN** runtime 已通过直连文件导入按钮设置文件
- **THEN** 步骤 MUST 等待页面暴露可识别的导入成功或失败结果
- **AND** 步骤成功时 MUST 在 `data.import_results` 中记录每个文件的 `file`、`status` 和 `message`

#### Scenario: 直连上传缺少结果时失败
- **WHEN** runtime 已通过直连文件导入按钮设置文件，但超时前没有识别到导入结果
- **THEN** `import.upload` MUST 失败
- **AND** 失败诊断 MUST 包含页面文本，并在可用时包含截图
