## Why

`table_row_selection.select target.first_available` 当前隐含“目标表必须有可勾选行选择控件”的前提。真实页面 `到账款项发布` 的弹窗明细表有可点击业务行但没有 checkbox，使用者自然写 `first_available: true` 时会失败，必须改成 `match` 才能工作，这个约束不友好且不一致。

## What Changes

- 扩展 `table_row_selection.select target.first_available` 的语义：在已解析的目标表格内，若第一条有效业务行没有 checkbox 或等效选择控件，runtime 应点击该业务行触发表格原生选中/高亮。
- 保持有 checkbox 的表格优先点击选择控件，避免改变常规勾选表格行为。
- 保持多表格作用域规则不变：多表格页面仍应使用 `target.table` 或可唯一推断的表格作用域。
- 增强失败诊断，区分“目标表格无有效业务行”和“找到业务行但无法完成选择”。

## Capabilities

### New Capabilities

### Modified Capabilities
- `table-row-selection`: 补齐 `target.first_available` 在无 checkbox 可点击业务行表格中的选择语义。

## Impact

- 影响 `ydf_browser/executor.py` 中 `first_available` 到运行时行号选择的分流。
- 影响 `ydf_browser/runtime.py` 中按序号选择表格行时的无 checkbox 兜底点击。
- 需要补充 executor/runtime 单元测试，并用 `流程-单位收入管理-到账款项发布流程 - 001.yaml` 的截断真实流程验证到生成发布明细；最终保存动作按验证需要谨慎执行。
