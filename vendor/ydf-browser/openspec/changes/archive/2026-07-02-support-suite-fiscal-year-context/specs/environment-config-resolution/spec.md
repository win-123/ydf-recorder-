## ADDED Requirements

### Requirement: 业务年度端点使用合并后的环境 base URL
ydf-browser MUST 在调用业务年度切换端点时使用已解析合并后的环境配置。

#### Scenario: 业务年度切换使用配置后的 base URL
- **WHEN** 配置加载将 `ydf.base_url` 解析为 `https://t9i-ydf.yonyougov.top`，且真实运行 suite 声明 `fiscal_year: "2027"`
- **THEN** 业务年度切换请求 SHALL 发送到 `https://t9i-ydf.yonyougov.top/yondif-ams-be/context/switch/fiscal/year?fiscalYear=2027`
- **AND** 除非其它 URL 是已解析合并后的 `base_url`，否则该请求 SHALL NOT 使用其它 base URL

#### Scenario: 环境配置可以覆盖业务年度端点
- **WHEN** 已选环境配置覆盖 `endpoints.switch_fiscal_year`
- **THEN** ydf-browser SHALL 使用覆盖后的端点路径和已解析合并后的 `base_url`
- **AND** 租户上下文、默认组织、菜单网关、模板匹配和浏览器导航 SHALL 继续使用同一个已解析环境
