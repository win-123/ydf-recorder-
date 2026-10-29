## Why

`open_menu` 当前在浏览器打开菜单前通过 API 会话预取服务详情和初始模板，但菜单页面随后会再次请求相同信息，造成串行等待、重复后端负载，并可能让执行器短暂使用与页面真实请求不一致的模板。运行时已经能够捕获页面模板响应，应让页面实际响应成为单据页 manifest 的唯一事实源。

## What Changes

- 移除真实 `open_menu` 路径中浏览器导航前的服务详情和 `matchingTemplate` 预取，直接打开 `/#/service/<serviceCode>`。
- 捕获菜单页面自身发出的服务详情及 `matchingTemplate` / `getTemplateBody` 响应，用于补全菜单元数据、构建初始 manifest 和刷新动态模板。
- 保留业务错误响应的 `message`、`code`、`displayCode` 和 `traceId`；技术错误允许页面重试，只有达到步骤总超时仍无有效模板时才失败。
- 非单据页面只有在页面实际服务元数据明确证明不是 BillRender 时才采用 open-only；不得以“未捕获模板”作为成功依据。
- 调整 `open_menu` 分阶段计时，使页面模板响应等待属于浏览器触发后的菜单业务稳定耗时，不再记录未执行的前置模板获取阶段。
- 保留显式模板获取和页面分析命令使用的 `YondifGateway.fetch_template()`，仅删除真实 DSL 运行中的重复调用。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `runtime-action-completion-signals`: `open_menu` 改为消费菜单页面实际返回的初始模板和服务元数据，同时保持工作面初始终态、错误传播和 open-only 的 fail-closed 语义。
- `lightweight-execution-timing`: `open_menu` 的模板等待从浏览器触发前准备改为浏览器触发后的实际页面阶段，并相应调整报告阶段字段。

## Impact

- 运行时与执行层：`ydf_browser/runtime.py`、`ydf_browser/executor.py`。
- 报告计时及相关测试：`tests/test_runtime.py`、`tests/test_executor.py`，必要时同步性能工作簿测试。
- OpenSpec 主规格：`runtime-action-completion-signals`、`lightweight-execution-timing`。
- 不新增 DSL 字段、配置项或第三方依赖；显式 `template fetch` 和 `page analyze` 命令保持现状。
