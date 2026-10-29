## ADDED Requirements

### Requirement: 菜单和查询错误不得从步骤证据消失
系统 SHALL 在 `open_menu` 成功时保留等待期间捕获的有效 page error 诊断，并 MUST 让 `query.search` 复用点击动作的未处理 error notification 语义；孤立 page error 继续不得单独改变已就绪工作面的成功结论。

#### Scenario: 工作面就绪但存在孤立页面错误
- **WHEN** `open_menu` 等待期间捕获到有效 page error，且目标工作面随后进入初始终态
- **THEN** `open_menu` SHALL 保持成功
- **AND** 步骤数据 MUST 包含本轮去重后的 `page_errors`

#### Scenario: 查询后出现未处理错误提示
- **WHEN** `query.search` 捕获到 error notification，且下一步不是 `notification.assert`
- **THEN** 查询步骤 MUST 失败并保留该提示
- **AND** 系统 MUST NOT 把查询完成信号解释为业务查询成功

#### Scenario: 查询错误是预期结果
- **WHEN** `query.search` 捕获到 error notification，且下一步紧接 `notification.assert`
- **THEN** 查询步骤 SHALL 保持成功以便下一步断言该提示
