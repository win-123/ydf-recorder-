## Context

平台 `YDFReferSelect` 将 `uidata/link` 交给 `ViewModal`。开启 `caninput` 时，`AutoComplete.onChange` 直接提交字符串；参照按钮仍用于显式选择。此前为银行树参照移除通用输入捷径，误伤了这一语义。

## Goals / Non-Goals

目标是在共享表单入口区分平台明确支持的自由输入与候选选择。不改变查询、可编辑表格、树参照和表格参照行为，不添加页面名称判断。

## Decisions

在 `fill_form_field` 已完成字段定位后，仅对 `YDFReferSelect`、`props.referType` 为 `uidata/link`、`props.caninput` 明确开启及标量目标组合启用自由输入。结构化目标仍交给现有参照模块。

使用浏览器原生输入与失焦，再复用字段值确认；不通过写 DOM 属性伪造回填。以真实页面最小用例和原始保存后查询用例确认业务值保留。

拒绝恢复所有 `caninput` 参照的旧捷径：树和表格组件可能需要选中候选才能回填关联属性。

## Risks / Trade-offs

- 搜索框文本未提交的风险 → 原生输入、失焦、读回及原始保存后查询共同验证。
- 放宽其它参照的风险 → 覆盖未开启输入、其它参照类型及结构化目标的原有选择路径。
