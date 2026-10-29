## Why

同一个运行时表格组件可能在外层组件容器和内层 `wui-table` 上重复使用同一 identity。当前 `open_menu` 会把这两个嵌套 DOM 根当成两个独立工作面；当外层已显示明确空结果而内层无法独立识别空状态时，菜单会错误等待到步骤超时。

## What Changes

- 工作面根发现按逻辑 identity 去除嵌套重复根，保留能够覆盖组件加载、业务行和明确空状态的最外层组件根。
- 不相互包含的同 identity 可见实例继续作为独立工作面参与等待，不放宽多工作面全部进入初始终态的要求。
- 增加嵌套重复表格根和明确空结果的回归覆盖，并使用真实合同审核菜单验证后续步骤能够开始执行。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `runtime-action-completion-signals`: 明确同一 identity 的嵌套 DOM 根只代表一个首次展示工作面，不能因内部重复根缺少独立空状态而阻塞 `open_menu`。

## Impact

- 运行时：`ydf_browser/runtime.py` 的首次展示工作面根发现。
- 测试：工作面采集和 `open_menu` 初始终态回归测试。
- DSL、CLI 参数和报告字段保持兼容，不新增依赖。
