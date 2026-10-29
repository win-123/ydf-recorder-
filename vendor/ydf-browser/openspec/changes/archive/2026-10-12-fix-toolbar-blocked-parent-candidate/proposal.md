## Why

二上二级项目细化的政府采购明细页点击“确定”时，运行时选择了被前景表格遮挡的父页面同名按钮。身份查找提前返回遮挡候选，阻止后续精确文本查找选择真实可点击的前景动作。

## What Changes

- 工具栏身份查找先返回可点击候选，遮挡候选留到全部可点击查找失败后用于诊断。
- 保持动作标签、别名、表格作用域及禁止强制点击的规则。
- 明细确认关闭后，当前工具栏动态弹窗仍有按模板身份绑定的可编辑字段时保留该弹窗模板，避免误恢复到更外层页面。
- 增加主页面和子 frame 的真实浏览器回归、失败派生真实 DSL。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `toolbar-action-clicking`：补充被遮挡父动作与不同身份前景同名动作并存时的候选优先级。
- `dynamic-template-context-restoration`：补充明细确认后仍活跃的父弹窗模板保留。

## Impact

涉及 `ydf_browser/runtime.py` 的工具栏候选解析、`ydf_browser/template_restoration.py` 的当前活动面保护、对应回归、`tests/real_cases/` 和工具栏使用说明。保持 DSL schema 和公共参数不变，不新增依赖。
