## Why

部分 YonDiF 菜单和单据数据依赖当前业务年度。现有 DSL 只能设置租户和默认组织，运行前无法声明业务年度，导致同一套用例在不同年度上下文下打开菜单或查询数据时结果不稳定。

## What Changes

- 在 suite 级 DSL 中增加可选 `fiscal_year` 字段，例如 `fiscal_year: "2027"`。
- 真实运行时如果配置了 `suite.fiscal_year`，在打开菜单前调用年度切换接口 `/yondif-ams-be/context/switch/fiscal/year?fiscalYear=<业务年度>`。
- 未配置或配置为空时保持现有行为，不额外调用年度切换接口。
- 年度切换失败时阻断后续菜单打开和业务步骤，避免在错误上下文中继续执行。

## Capabilities

### New Capabilities
- `suite-fiscal-year-context`: 定义 suite 级业务年度上下文的 DSL 表达、接口切换时机和缺省忽略行为。

### Modified Capabilities
- `environment-config-resolution`: 年度切换接口作为环境端点配置的一部分，真实运行应使用已解析的 `base_url`。

## Impact

- DSL 解析和报告中的 `DslTestSuite` 结构会增加 `fiscal_year` 字段。
- 真实运行登录上下文准备链路会增加一个可选年度切换调用，位置在最终登录和菜单解析/打开之间。
- 环境端点配置会增加 `switch_fiscal_year` 默认值；不引入新依赖。
- 需要补充 DSL、上下文调用和 CLI 真实运行参数传递的单元测试，并更新 README 或示例说明。
