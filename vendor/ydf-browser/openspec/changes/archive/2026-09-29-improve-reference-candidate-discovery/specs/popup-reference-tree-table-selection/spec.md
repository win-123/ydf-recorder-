## ADDED Requirements

### Requirement: 探索与测试 DSL 分离
系统 MUST 保持测试 DSL 不变，不提供 popup_reference.discover 操作。未开启探索参数时 MUST NOT 主动展开参照。

#### Scenario: 观察当前已渲染候选
- **WHEN** 用户仅开启 --ai-observe
- **THEN** 页面摘要 MUST 提供当前前景参照的有界候选、路径、结构末级和可选性证据
- **AND** 采集 MUST NOT 展开、过滤、选择或确认参照

#### Scenario: 显式末尾探索
- **WHEN** 用户配合 --ai-observe 指定 --explore-reference JSON 且用例成功结束
- **THEN** 系统 MUST 只对当前已经打开的前景参照执行有界路径展开或过滤
- **AND** 系统 MUST NOT 选择、确认、保存或重放业务步骤
- **AND** 探索状态 MUST 单独写入末步 data.reference_exploration，不改变原测试结果

#### Scenario: 用例失败或没有打开参照
- **WHEN** 用例执行失败或结束时没有参照
- **THEN** 系统 MUST 分别报告探索跳过或探索失败
- **AND** 系统 MUST NOT 自动打开其它业务页面

#### Scenario: 参数与覆盖范围
- **WHEN** 路径不是最多 32 个非空文本、offset 为负数、limit 不在 1 到 500、包含未知字段或未开启观察
- **THEN** CLI MUST 在执行前拒绝该探索参数
- **WHEN** 返回已渲染候选
- **THEN** 系统 MUST 明确报告范围、截断和继续发现方式，不将报告分页解释为后台全集分页

#### Scenario: 候选表格的隐藏和敏感内容
- **WHEN** 当前参照表格包含隐藏单元格或具有敏感身份的可见单元格
- **THEN** 候选证据 MUST 排除隐藏内容，并对敏感单元格脱敏
- **AND** 行文本和路径 MUST NOT 保留敏感内容副本

### Requirement: 参照选择拒绝保留真实原因
系统 MUST 在当前参照选择收到新的警告或错误拒绝通知时保留该原因、目标与通知，不得只报告弹窗未关闭。

#### Scenario: 选择父节点被末级规则拒绝
- **WHEN** 当前选择或确认触发请选择末级节点的拒绝通知
- **THEN** 当前步骤 MUST 失败并在主错误中保留该消息
- **AND** 结构化证据 MUST 包含选择目标与拒绝通知
- **AND** 系统 MUST NOT 自动更换业务候选

#### Scenario: 旧通知不属于本次拒绝
- **WHEN** 参照开始选择前已有警告且当前选择成功回填
- **THEN** 系统 MUST NOT 将旧警告归因于本次参照选择

#### Scenario: 新拒绝与旧提示文案相同
- **WHEN** 当前选择产生新的通知节点，其警告文案与选择开始前的提示相同
- **THEN** 系统 MUST 将新通知保留为本次拒绝
- **AND** 原有节点因无关页面变更被重新扫描时 MUST NOT 被认作新拒绝
