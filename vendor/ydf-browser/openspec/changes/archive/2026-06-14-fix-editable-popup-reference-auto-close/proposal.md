## Why

真实用例 `/Users/ken/temp/ydf-browser-问题反馈/功能-网上报销-报销管理-还款单填报-按钮-0011.yaml` 在 `editable_table.fill_row` 录入 `汇款转账.收款方户名` 时失败。诊断截图显示 `YDFReferSelect` 参照已经选择并回填到表格行，但运行时仍误判参照弹窗未关闭，继续查找确认按钮并报错。

这会让已经完成业务录入的可编辑表格参照列被报告为失败，阻断还款单填报这类真实 YonDiF 单据链路。

## What Changes

- `editable_table.fill_row` 在录入可编辑表格参照列时，必须正确识别“候选参照已关闭且目标单元格已回填”的状态，并直接完成当前字段录入。
- 弹出参照的“仍可见”判断必须限定在真实参照候选层或参照弹窗根内，不能因为背景编辑页或底部工具栏存在 `保存` 按钮就误认为参照还在。
- 参照选择后若已回填目标单元格，运行时不得继续点击背景页面的 `保存`、不得继续要求 `确定/确认`，也不得把页面级保存按钮当作参照确认入口。
- 增加回归测试覆盖：可编辑表格 `YDFReferSelect` 选择后自动关闭候选层、页面自身仍有 `保存` 按钮时，`editable_table.fill_row` 应成功返回。
- 使用真实用例重新验证，确认至少越过 `汇款转账.收款方户名` 录入步骤；如后续保存受业务数据 warning 影响，应在交付说明中区分工具修复和业务数据问题。

## Capabilities

### New Capabilities
- 无。

### Modified Capabilities
- `editable-table-cell-entry`: 补充可编辑表格参照列录入的自动关闭、回填判定和背景按钮隔离要求。

## Impact

- 影响 `ydf_browser/runtime.py` 中可编辑表格参照列录入、弹出参照关闭判定、回填等待和确认按钮查找逻辑。
- 影响 `tests/test_runtime.py` 中弹出参照、可编辑表格参照列和确认按钮误判相关回归测试。
- 不改变 DSL 语法；现有 `{filter, first_available}`、`row_number`、`match` 等结构化参照写法保持兼容。
- 不改变页面级 `toolbar.click 保存` 语义；页面保存按钮仍由工具栏动作处理。
