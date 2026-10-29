## Why

YonDiF 动态抽屉切换后可能同时保留多个可见、同 `fieldid` 的表单实例。当前运行时选择 DOM 顺序中的第一个可见实例，可能把值写入已被前景层遮挡、无法接收 pointer 的旧抽屉；报告读回成功，但当前业务表单仍为空。

## What Changes

- 表单字段存在多个同身份可见实例时，优先选择真实可接收 pointer 的输入控件所在根节点。
- 即使已有绑定标记为 `in_dialog=true`，录入前仍按当前 DOM 重新解析可交互前景实例，避免复用旧抽屉绑定。
- 没有可接收 pointer 的同身份实例时保持现有前景、标签和身份回退，不扩大到全页面裸文本定位。
- 不改变 DSL 写法，不增加页面、菜单或字段名特例。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `form-field-entry`: 同身份前景表单实例冲突时增加可接收 pointer 的硬优先级，并在录入前重新解析当前实例。

## Impact

- 运行时：`ydf_browser/runtime.py` 的前景表单字段根解析链路。
- 测试：`tests/test_runtime.py` 的同 `fieldid` 旧抽屉与当前抽屉候选场景。
- 规格：`form-field-entry` 的表单字段录入确认语义。
- 无新增依赖，无 DSL schema 变更。
