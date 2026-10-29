## 1. DSL and config model

- [x] 1.1 在 `DslTestSuite` 增加 `fiscal_year` 字段，并确保 `to_dict()` 报告输出包含该字段。
- [x] 1.2 更新 DSL loader 解析 `suite.fiscal_year`，保持缺省或空值为忽略状态。
- [x] 1.3 在 `EndpointConfig` 增加 `switch_fiscal_year` 默认端点，并允许环境配置覆盖。

## 2. 业务年度上下文切换

- [x] 2.1 增加最小年度切换上下文实现，使用当前 `EnvironmentConfig.base_url` 和 `endpoints.switch_fiscal_year` 调用接口。
- [x] 2.2 在真实运行登录上下文准备链路中传递 `suite.fiscal_year`，并在最终登录后、菜单解析前执行年度切换。
- [x] 2.3 年度切换 HTTP 失败或返回 `success=false` 时，让 case setup 失败并报告“设置业务年度失败”类错误。
- [x] 2.4 未配置 `suite.fiscal_year` 时不调用年度切换接口，保持现有租户、组织和菜单打开流程。

## 3. Tests

- [x] 3.1 增加 DSL 单测，覆盖 `suite.fiscal_year` 解析、序列化和缺省忽略。
- [x] 3.2 增加年度上下文单测，覆盖 URL 拼接、端点 override、空值跳过和失败响应。
- [x] 3.3 增加 CLI/真实运行接线单测，证明 `suite.fiscal_year` 会传入登录上下文准备链路，且调用顺序在菜单解析前。
- [x] 3.4 回归现有租户和默认组织上下文单测，确认未配置业务年度时行为不变。

## 4. Docs and verification

- [x] 4.1 更新 README 或示例文档，说明 `suite.fiscal_year` 的可选用法。
- [x] 4.2 运行 `openspec validate support-suite-fiscal-year-context --strict` 和 `./scripts/check_openspec_language.py --change support-suite-fiscal-year-context`。
- [x] 4.3 运行相关 pytest：`tests/test_dsl.py`、`tests/test_cli.py`、新增年度上下文测试，以及受影响上下文测试。
- [x] 4.4 使用包含 `suite.fiscal_year: "2027"` 的最小真实 `open_menu` 用例验证年度切换在打开菜单前执行；如环境不可用，保留失败证据和后续验证入口。
