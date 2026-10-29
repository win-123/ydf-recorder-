## MODIFIED Requirements

### Requirement: 菜单打开前切换业务年度
ydf-browser MUST 在真实浏览器执行解析或打开 case 的首个菜单前确认已声明的 suite 业务年度；实际年度不符时 SHALL 在有效会话上完成切换并验证，不以年度变化为由重新提交密码。

#### Scenario: 已配置业务年度在 open_menu 前切换
- **WHEN** 真实运行的 case 所属 suite 配置了 `fiscal_year: "2027"`，且当前年度不是 `2027` 或尚不能确认
- **THEN** ydf-browser SHALL 使用当前认证 session，在解析或打开 case 菜单前调用 `/yondif-ams-be/context/switch/fiscal/year?fiscalYear=2027`
- **AND** case SHALL 仅在切换成功且最终业务年度符合要求后继续执行

#### Scenario: 当前年度已经符合
- **WHEN** 当前有效会话的实际业务年度经验证与 suite 声明相同
- **THEN** 系统 SHALL 跳过重复年度切换

#### Scenario: 业务年度切换使用最终登录上下文
- **WHEN** 真实运行已建立有效认证会话并完成租户或默认组织上下文刷新
- **THEN** ydf-browser SHALL 在该最终有效会话上按需切换业务年度
- **AND** ydf-browser SHALL 在 case 的菜单解析、模板匹配或浏览器菜单导航前完成年度准备

#### Scenario: 未配置业务年度时跳过切换调用
- **WHEN** 真实运行的 suite 未配置 `suite.fiscal_year`
- **THEN** ydf-browser SHALL NOT 调用业务年度切换端点
- **AND** ydf-browser SHALL 沿用系统当前年度，包括之前用例设置的年度，而不主动恢复默认年度
