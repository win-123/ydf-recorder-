## MODIFIED Requirements

### Requirement: 直连文件导入按钮
`import.upload` SHALL 支持点击后直接打开浏览器 file chooser 的 YonDiF 导入动作，而不要求这类动作必须打开平台公共导入工作台。

#### Scenario: YDFileImportButton 直连上传
- **WHEN** DSL 执行 `component: import`、`operation: upload`，并且 `target.label` 或 `target.fieldid` 绑定到可见的 `YDFileImportButton` 或等价直连文件导入按钮
- **THEN** runtime MUST 点击该业务按钮并捕获浏览器 file chooser
- **AND** runtime MUST 将 `target.file` 或 `target.files` 指定的文件设置到该 file chooser
- **AND** runtime MUST NOT 尝试打开公共导入组件的下拉子按钮或导入工作台

#### Scenario: 运行时识别直连上传
- **WHEN** DSL 执行 `component: import`、`operation: upload`，并且 `target.label` 或 `target.fieldid` 绑定的可见业务动作点击后触发 file chooser
- **THEN** runtime MUST 将该动作识别为直连文件导入按钮
- **AND** runtime MUST 将 `target.file` 或 `target.files` 指定的文件设置到该 file chooser
- **AND** runtime MUST NOT 尝试打开公共导入组件的下拉子按钮或导入工作台

#### Scenario: 模板身份不是直连入口的唯一条件
- **WHEN** 目标业务动作未标识为 `YDFileImportButton` 且没有 `justFile` 属性，但点击后真实触发 file chooser
- **THEN** runtime MUST 仍按直连文件导入处理
- **AND** runtime MUST NOT 要求 DSL 提供入口模式或组件类型

#### Scenario: 公共导入保持兼容
- **WHEN** DSL 执行 `import.upload`，并且目标导入动作打开公共导入菜单或工作台而没有直接触发 file chooser
- **THEN** runtime MUST 保持现有公共导入组件流程
- **AND** runtime MUST 继续通过导入工作台选择文件、提交导入并等待结果

#### Scenario: 入口形态无法识别
- **WHEN** 目标业务动作既没有触发 file chooser，也没有打开可识别的公共导入界面
- **THEN** `import.upload` MUST 失败
- **AND** 失败诊断 MUST 包含页面文本，并在可用时包含截图

### Requirement: 导入上传报告业务结果
`import.upload` SHALL 在文件选择后报告可观察的导入业务结果；直连入口在业务结果不透明时可以显式报告 `submitted`，公共导入入口仍必须报告 `success` 或 `failure`。

#### Scenario: 直连上传等待结果
- **WHEN** runtime 已通过直连文件导入按钮设置文件，相关后端上传或解析响应包含可识别的业务成功或失败结果
- **THEN** 步骤 MUST 在 `data.import_results` 中记录每个文件的 `file`、`status` 和 `message`
- **AND** `status` MUST 为 `success` 或 `failure`

#### Scenario: 直连上传显式接受已提交
- **WHEN** DSL 显式设置 `target.assert.status: submitted`
- **AND** runtime 已通过直连文件导入按钮设置文件
- **AND** 相关后端上传或解析请求成功完成，但响应没有可识别的业务成功或失败结果
- **THEN** 步骤 MUST 在 `data.import_results` 中记录每个文件的 `file`、`status: submitted` 和说明信息
- **AND** 步骤 MUST NOT 继续等待公共导入进度界面直至默认结果超时

#### Scenario: 明确成功满足已提交期望
- **WHEN** DSL 显式设置 `target.assert.status: submitted`
- **AND** runtime 识别到相关后端处理的明确业务成功结果
- **THEN** `success` MUST 满足该步骤对 `submitted` 的最低期望
- **AND** 报告 MUST 保留实际 `status: success`

#### Scenario: 明确失败不满足已提交期望
- **WHEN** DSL 显式设置 `target.assert.status: submitted`
- **AND** runtime 捕获到请求失败、HTTP 非成功状态或明确的业务失败结果
- **THEN** `import.upload` MUST 失败
- **AND** runtime MUST NOT 将失败降级为 `submitted`

#### Scenario: 未显式接受已提交
- **WHEN** DSL 未设置 `target.assert.status` 或设置为 `success`
- **AND** runtime 只能确认相关后端请求成功完成而不能识别业务结果
- **THEN** `import.upload` MUST 失败
- **AND** 失败信息 MUST 说明当前证据只足以判定 `submitted`

#### Scenario: 公共导入不允许已提交
- **WHEN** `import.upload` 识别到公共导入组件入口
- **THEN** runtime MUST 继续等待并报告 `success` 或 `failure`
- **AND** runtime MUST NOT 以 `submitted` 结束公共导入步骤

#### Scenario: 直连上传缺少结果时失败
- **WHEN** runtime 已通过直连文件导入按钮设置文件，但超时前没有观察到与该交互相关的后端上传或解析请求
- **THEN** `import.upload` MUST 失败
- **AND** 失败诊断 MUST 包含网络请求摘要、页面文本，并在可用时包含截图

## ADDED Requirements

### Requirement: 已提交导入必须有后置业务断言
DSL 校验器 MUST 要求显式期待 `submitted` 的 `import.upload` 后存在业务断言，避免用“导入已提交”代替业务成功验证。

#### Scenario: 已提交位于用例末尾
- **WHEN** `import.upload` 设置 `target.assert.status: submitted` 且它是用例最后一步
- **THEN** DSL 校验 MUST 失败
- **AND** 错误信息 MUST 要求增加后置业务断言

#### Scenario: 已提交后没有业务断言
- **WHEN** `import.upload` 设置 `target.assert.status: submitted`
- **AND** 后续步骤中没有已知的表格、表单、通知或其他组件业务断言
- **THEN** DSL 校验 MUST 失败
- **AND** 错误信息 MUST 列出可用的业务断言方向

#### Scenario: 已提交后存在业务断言
- **WHEN** `import.upload` 设置 `target.assert.status: submitted`
- **AND** 后续步骤中存在至少一个受支持的业务断言
- **THEN** DSL 校验 MUST 通过该跨步骤门禁
- **AND** 业务断言 MAY 位于必要的页签切换或结果区域展开步骤之后
