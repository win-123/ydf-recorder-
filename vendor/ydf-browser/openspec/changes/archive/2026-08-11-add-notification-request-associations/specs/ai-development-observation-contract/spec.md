## ADDED Requirements

### Requirement: 错误提示必须关联候选业务请求
系统 MUST 在 AI 观察模式下，为由未处理 error notification 触发的非通过失败证据包生成 `notification_request_associations`，表达页面错误提示与业务 API 请求之间的确定性关联或未决候选关系。

#### Scenario: 声明错误提示关联能力
- **WHEN** skill 运行 `ydf-browser doctor --skip-config` 或读取 AI 观察运行的 `run_started`
- **THEN** `capabilities.available` 或 `capabilities.enabled` MUST 包含 `notification_request_associations`
- **AND** `contract_version` MUST 使用兼容 minor 版本表达该新增字段

#### Scenario: 确认 YonDiF 统一业务错误响应
- **WHEN** 当前失败步骤因未处理 `type=error` 页面提示失败
- **AND** 失败证据候选范围内存在唯一已完成业务请求，其脱敏 JSON 响应正文满足 `code === 999`
- **AND** 该响应正文的 `message` 与页面提示文本精确一致
- **THEN** 失败证据包 MUST 包含一条 `status=confirmed` 的 `notification_request_associations` 记录
- **AND** 该记录 MUST 包含提示类型与文本、`evidence_basis=yondif_code_999_message_exact`、`request_id`、HTTP 方法、响应状态、浏览器原始 URL、实际请求 URL、转发结果摘要，以及响应正文路径

#### Scenario: 未决候选不排序
- **WHEN** 页面错误提示附近存在业务请求，但不存在唯一确定性正文匹配或共同请求标识证据
- **THEN** 失败证据包 MUST 包含 `status=unresolved` 的关联记录
- **AND** 该记录 MUST 包含未决原因和候选 `request_id`
- **AND** 系统 MUST NOT 根据 HTTP 状态、URL 相似性、时间邻近或通用 HTTP 200 业务 envelope 生成“最可能请求”或根因判断

#### Scenario: 候选范围沿用失败证据窗口
- **WHEN** 系统为错误提示生成关联候选
- **THEN** 候选范围 MUST 复用失败步骤开始前 5 秒至结束后 5 秒内开始或完成的业务请求
- **AND** 在失败步骤内已启动但证据包生成时尚未完成的请求 MUST 以候选 `request_id` 保留，并记录终态或正文不可用原因
- **AND** 系统 MUST NOT 为等待后置响应额外延迟失败收尾

#### Scenario: 保持失败请求摘要兼容
- **WHEN** HTTP 200 业务响应因错误提示关联进入 `notification_request_associations`
- **THEN** 系统 MUST NOT 仅因该业务响应表示错误而把它加入 `failed_requests`
- **AND** `failed_requests` MUST 继续只表达网络失败、不完整请求或 HTTP 非成功状态的既有摘要语义

#### Scenario: 预期错误提示不触发关联失败包
- **WHEN** 点击动作捕获 error notification 且下一步紧接 `notification.assert` 将其声明为预期结果
- **THEN** 当前点击步骤 MUST 保持成功
- **AND** 系统 MUST NOT 仅因该预期提示生成失败证据包或 `notification_request_associations`
