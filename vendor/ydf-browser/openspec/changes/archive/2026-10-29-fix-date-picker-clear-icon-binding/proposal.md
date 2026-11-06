## Why

单位账户开立页面的日期字段有默认值时，绑定会把清空图标作为日期录入目标。日期写入器向图标写入 `title`，写后确认又读回这个属性，导致 `form.fill` 报告成功，而真实输入框仍保留原值。

## What Changes

- 日期字段同根候选归并只接受真实日期控件容器，排除清空图标等装饰；多个控件仍保持不兼容。
- 日期录入只向真实输入框写值，并以输入框实际值确认，不能用自行写入的 `title` 证明成功。
- 增加完整扫描、绑定、录入回读回归和失败报告派生的真实 DSL，保留原来成功的核准日期对照。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `form-field-entry`：明确日期字段的真实输入写入与回读要求，以及清空图标和多控件歧义边界。

## Impact

涉及 `ydf_browser/binder.py`、`ydf_browser/runtime.py`、对应 pytest、真实回归 DSL 和表单录入规格。不新增 DSL 字段、依赖或页面专用分支，不执行保存或提交。
