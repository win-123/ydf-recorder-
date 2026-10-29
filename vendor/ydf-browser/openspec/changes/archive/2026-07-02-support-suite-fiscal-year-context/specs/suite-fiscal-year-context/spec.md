## ADDED Requirements

### Requirement: Suite 业务年度字段
ydf-browser SHALL 允许测试集 DSL 在 `suite.fiscal_year` 声明可选业务年度，该值适用于当前 suite 的全部 case。

#### Scenario: DSL 解析保留 suite 业务年度
- **WHEN** suite DSL 在 `suite` 下声明 `fiscal_year: "2027"`
- **THEN** DSL 加载结果 SHALL 在 suite 上保存 `"2027"`
- **AND** suite 序列化结果 SHALL 包含 `fiscal_year: "2027"`

#### Scenario: 缺省 suite 业务年度被忽略
- **WHEN** suite DSL 省略 `suite.fiscal_year` 或将其配置为空值
- **THEN** DSL 加载结果 SHALL 保持 suite 业务年度为空
- **AND** 校验 SHALL NOT 要求必须配置业务年度

### Requirement: 菜单打开前切换业务年度
ydf-browser MUST 在真实浏览器执行解析或打开 case 的首个菜单前，切换已配置的 suite 业务年度。

#### Scenario: 已配置业务年度在 open_menu 前切换
- **WHEN** 真实运行的 case 所属 suite 配置了 `fiscal_year: "2027"`
- **THEN** ydf-browser SHALL 使用当前认证 session，在解析或打开 case 菜单前调用 `/yondif-ams-be/context/switch/fiscal/year?fiscalYear=2027`
- **AND** case SHALL 仅在切换请求成功后继续执行

#### Scenario: 业务年度切换使用最终登录上下文
- **WHEN** 真实运行已应用租户或默认组织上下文，并完成所需的后续登录
- **THEN** ydf-browser SHALL 在该后续登录完成后切换业务年度
- **AND** ydf-browser SHALL 在 case 的菜单解析、模板匹配或浏览器菜单导航前切换业务年度

#### Scenario: 未配置业务年度时跳过切换调用
- **WHEN** 真实运行的 suite 未配置 `suite.fiscal_year`
- **THEN** ydf-browser SHALL NOT 调用业务年度切换端点
- **AND** 现有租户、默认组织、菜单和浏览器执行流程 SHALL 保持不变

### Requirement: 业务年度切换失败会停止执行
ydf-browser MUST 将业务年度切换失败视为受影响 case 的 setup 失败。

#### Scenario: 业务年度切换端点失败
- **WHEN** 已配置 `suite.fiscal_year`，且业务年度切换请求返回 HTTP 错误或响应载荷包含 `success=false`
- **THEN** 受影响 case SHALL 在任何业务步骤执行前失败
- **AND** 错误信息 SHALL 表明设置业务年度失败
