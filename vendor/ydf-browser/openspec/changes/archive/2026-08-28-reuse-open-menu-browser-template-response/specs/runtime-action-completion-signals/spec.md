## ADDED Requirements

### Requirement: open_menu 使用菜单页面实际模板响应
`open_menu` SHALL 在解析出 `serviceCode` 后直接触发浏览器菜单路由，并使用菜单页面自身返回的服务详情和模板响应建立初始 manifest；系统 MUST NOT 在浏览器触发前独立发送同一服务详情或模板请求。

#### Scenario: 页面返回有效初始模板
- **WHEN** 菜单页面请求服务详情并通过 `matchingTemplate` 或 `getTemplateBody` 返回可构建 manifest 的模板
- **THEN** `open_menu` MUST 使用该页面实际响应构建 manifest
- **AND** 系统 MUST 继续等待对应首次展示工作面进入初始终态后再执行绑定

#### Scenario: 页面模板返回业务错误
- **WHEN** 菜单页面的模板响应返回明确业务失败码和错误消息且没有有效模板
- **THEN** `open_menu` MUST 立即失败并保留响应中的 `message`、`code`、`displayCode` 和 `traceId`
- **AND** 系统 MUST NOT 将该响应丢弃后退化为通用超时或 open-only 成功

#### Scenario: 模板技术错误后页面重试成功
- **WHEN** 菜单页面的一次模板请求返回 HTTP 错误、非 JSON 响应或无法构建 manifest 的技术错误
- **AND** 页面随后在步骤总超时内返回有效模板并使工作面进入初始终态
- **THEN** `open_menu` SHALL 使用后续有效响应继续执行
- **AND** 先前技术错误 MUST 仅作为诊断证据保留

#### Scenario: 单据页面未返回有效模板
- **WHEN** 页面实际服务元数据表明目标使用 BillRender 单据模板
- **AND** 到达步骤总超时仍未捕获可构建 manifest 的页面模板响应
- **THEN** `open_menu` MUST 明确失败并报告模板响应不可用
- **AND** 系统 MUST NOT 重新发送独立模板请求作为隐式兜底

#### Scenario: 页面实际元数据确认非单据页面
- **WHEN** 菜单页面返回的服务元数据明确表明目标不使用 BillRender 单据模板
- **THEN** `open_menu` SHALL 按 open-only 语义继续校验菜单页签和业务承载
- **AND** 缺少模板响应本身 MUST NOT 成为 open-only 的判定依据

## MODIFIED Requirements

### Requirement: open_menu 超时和 open-only 边界明确
系统 SHALL 让菜单解析、浏览器打开、页面模板响应、页签校验、工作面等待和绑定共同消费一个步骤级总超时，默认上限为 120 秒；单据模板工作面未在总超时内就绪时 `open_menu` MUST 明确失败。

#### Scenario: 单据模板工作面超时
- **WHEN** 到达步骤级总超时时仍有首次展示工作面未挂载、仍在加载或没有进入初始终态
- **THEN** `open_menu` MUST 报告失败
- **AND** 失败数据 MUST 包含未就绪工作面及其最后状态

#### Scenario: 明确认定为非单据页面
- **WHEN** 平台菜单和服务元数据明确表明目标页面不使用单据模板
- **THEN** 系统 SHALL 按 open-only 语义在页签和业务承载建立后报告成功
- **AND** 后续组件级动作 MUST 继续明确拒绝该页面

#### Scenario: 页面模板技术错误未恢复
- **WHEN** 页面模板请求发生超时、HTTP 错误或响应无法解析，且到达步骤级总超时仍未返回有效模板
- **AND** 页面实际服务元数据没有明确认定目标为非单据页面
- **THEN** `open_menu` MUST 以页面初始模板响应不可用明确失败
- **AND** 系统 MUST NOT 把技术错误转换为 open-only 成功或重新发送独立模板请求

#### Scenario: 孤立 HTTP 失败后页面恢复
- **WHEN** `open_menu` 期间出现 HTTP 失败，但目标工作面没有业务错误状态并且随后正常进入初始终态
- **THEN** 系统 MUST NOT 因该孤立 HTTP 失败立即判定步骤失败
- **AND** 请求失败 MUST 保留为诊断证据

#### Scenario: 工作面出现业务失败证据
- **WHEN** 目标工作面显示加载失败、可关联的业务错误提示或崩溃状态
- **THEN** `open_menu` MUST 立即失败，不再等待步骤总超时

#### Scenario: 页面错误没有目标工作面归属
- **WHEN** 页面抛出 JavaScript 错误，但目标工作面没有显示业务错误并且随后进入初始终态
- **THEN** 系统 MUST NOT 单独把该页面错误当作 `open_menu` 失败证据
- **AND** 页面错误 MUST 继续保留为诊断证据

#### Scenario: 页面错误后工作面仍然超时
- **WHEN** 页面抛出 JavaScript 错误，并且目标工作面到达步骤总超时时仍未进入初始终态
- **THEN** `open_menu` MUST 按工作面超时报告失败
- **AND** 失败数据 MUST 同时包含页面错误和最后工作面状态
