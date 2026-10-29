# Proposal

## Why

退回审批操作框没有单据模板，`form.fill` 的运行时绑定把“请选择退回环节”的标签当成输入框，导致 `first_available` 失败。固有字段与业务配置增加的简单字段应复用现有表单赋值语义。

## What Changes

- 修正无模板前景表单的字段发现、标签关联和控件类型识别，避免将标签本身当作输入框。
- 复用 `form.fill`、现有下拉和文本录入确认，以及显式 `dialog.cancel/confirm`；不增加工作流专用语法。
- 增加真实失败衍生的退回框回归，填写后读回并取消，不实际退回单据。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `form-field-entry`：明确无模板审批操作框中的真实控件绑定与录入确认边界。

## Impact

涉及 `ydf_browser/runtime.py`、`ydf_browser/binder.py` 及其调用入口的回归测试、真实 DSL 和表单使用说明。保留模板身份、弹出参照与现有 DSL schema；不修改业务系统代码或增加依赖。
