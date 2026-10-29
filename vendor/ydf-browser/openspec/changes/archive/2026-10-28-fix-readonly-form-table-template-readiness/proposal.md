## Why

领用分配行级动作已打开编辑页并返回有效模板，但基本信息字段全部为只读文本，没有输入控件的运行时身份。动态模板就绪检查仍强制要求表单字段出现，导致后续填写继续使用列表模板并报“表格名称未匹配”。

## What Changes

- 动态模板的可见表单字段全部明确声明 `props.readOnly` 时，以唯一可交互的目标表格证明工作面就绪。
- 保留可编辑字段延迟渲染、目标表格缺失、工作面歧义和遮挡时的拒绝边界。
- 补充聚焦回归和不保存、不出库的真实 DSL 用例。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `runtime-action-completion-signals`：明确只读基本信息与可交互表格共存时的动态模板就绪条件。

## Impact

影响 `ydf_browser/runtime.py` 的共享动态模板就绪判断、对应测试和 `tests/real_cases/`。不增加依赖、DSL 字段或配置，不改变业务保存和出库动作。
