## Why

`open_menu` 当前把菜单解析、浏览器触发、页面实际单据模板响应、首次展示工作面终态、绑定、证据和计时分散在 `WorkflowExecutor`、`PlaywrightRuntime` 及多个辅助 module 中，并通过可变 payload 和反射式调用交换状态。近期菜单就绪与模板响应变更反复同时修改 `runtime.py`、`executor.py` 及两组实现耦合测试，现在需要把该共享入口收拢为一个可独立验证的 deep module。

## What Changes

- 新增 `ydf_browser.menu_opening` deep module，以一次完整菜单打开操作作为外部 interface。
- 将菜单解析到初始工作面终态、manifest 构建、绑定、承载识别、证据和计时收进同一 implementation。
- 以不可变成功结果和结构化失败替代菜单打开期间的可变 payload side channel。
- 生产 adapter 只消费菜单页面实际返回的服务详情和单据模板；fixture adapter 直接提供内存模板。
- 删除 `WorkflowExecutor` 中菜单打开编排、私有轮询和假想 runtime 兼容分支；executor 只保留 DSL 路由、状态接收和报告映射。
- 将行为测试迁移到公开 module interface；Runtime 测试只保留浏览器 adapter 职责，executor 测试只保留路由和映射职责。
- 保持现有 DSL、报告字段、错误文本、contract path、计时、profile、失败现场和真实页面行为不变。

## Capabilities

### New Capabilities

无。本变更只调整内部 module 和 seam，不引入用户可见能力。

### Modified Capabilities

无。现有 `runtime-action-completion-signals`、`lightweight-execution-timing`、`menu-hosting-mode-detection`、`browser-profile-lifecycle` 及相关 requirements 保持不变。

## Impact

- 主要代码：新增 `ydf_browser/menu_opening.py`，收窄 `ydf_browser/executor.py` 与 `ydf_browser/runtime.py` 的菜单打开职责。
- 主要测试：新增 `tests/test_menu_opening.py`，删除或改写 `tests/test_executor.py` 与 `tests/test_runtime.py` 中穿过目标 interface 的实现耦合测试。
- 领域语言：`CONTEXT.md` 增加“菜单打开”。
- 外部兼容性：DSL、报告、命令行、真实页面行为和第三方依赖保持不变。
- 验证风险：菜单打开是所有组件级动作的共享入口，必须完成聚焦测试、全量 pytest 和两条真实 DSL 验证。
