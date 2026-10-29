## Why

集中支付新增页的支付摘要使用允许输入的 `YDFReferSelect`，但运行时强制打开参照并要求候选回填，导致唯一测试摘要无法录入。平台该组件的自由输入会直接提交字符串，需要按其真实语义处理。

## What Changes

- `form.fill` 对 `YDFReferSelect` 的 `uidata/link` 模式，仅在 `props.caninput` 明确开启且目标为标量时直接录入并确认。
- 保留结构化参照选择及树、表格参照原有语义。
- 补充快速回归和不保存的真实 DSL。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `form-field-entry`: 明确可输入页面参照的标量录入边界。

## Impact

影响 `ydf_browser/runtime.py` 的表单录入分流、对应测试及使用说明，不增加依赖或 DSL 字段。
