## Why

采购计划行编辑表单中的 `YDFTableModalSelect` 同一精确身份根同时暴露多个包装节点、只读输入和唯一可点击参照按钮。当前 binder 不把该按钮视为参照直接控件，导致 `form.fill` 在打开参照前错误报告“平台精确身份状态不兼容”；若只绑定按钮，runtime 又会从按钮而不是来源字段 owner 读取回填值。

## What Changes

- 仅在 `YDFTableModalSelect`、`YDFTreeModalSelect` 的同一精确身份根内，将唯一可见、未禁用、可接收 pointer 的参照按钮识别为直接控件。
- 同一精确身份根同时存在唯一可编辑输入和参照按钮时优先绑定输入；只有输入不可用时才绑定唯一按钮。
- 多个可用按钮、不同身份根或无法证明来源字段身份时继续失败，不按 DOM 顺序猜测。
- `form.fill` 操作弹出参照时优先恢复唯一前景字段 owner，并从该 owner 确认回填值；按钮只负责触发参照。
- 增加 binder 与 runtime 回归测试，并用原始真实 DSL 证明采购品目选择完成。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `form-field-entry`: 补充同一精确身份根内唯一弹出参照按钮的绑定，以及来源字段 owner 回填确认语义。

## Impact

- 代码：`ydf_browser/binder.py`、`ydf_browser/runtime.py`。
- 测试：`tests/test_binder.py`、`tests/test_runtime.py`。
- 规格：`openspec/specs/form-field-entry/spec.md` 的增量要求。
- 不改变 DSL schema、命令行接口或依赖。
