## Why

可编辑表格“收款人全称”打开参照弹窗后，运行时已勾选第一行候选，却把仍可见的嵌套 iframe 参照弹窗误判为已关闭并跳过“确定”，单元格保持“请选择”，最终报“弹出参照选择未回填到字段”。该问题在工具版本 0.1.32 与当前源码上均可用真实 DSL 复现（run `20260826-151034-19b606fa`），7 月归档修复只覆盖了旧页面形态，未覆盖 pvdf 嵌套 iframe 形态。

## What Changes

- 修改共享弹出参照关闭判定：当 dialog 外壳包含可见 iframe 时，将“候选面仍可见”的检查限定到该 dialog 所包含的 frame，而不是依赖页面 URL 或标题关键字猜测。
- 收紧跨 frame 候选面扫描：以同一搜索上下文内可见候选表格/树、`确定/确认/保存` 和 `取消` 的结构证据为判定基础，避免把仍打开的嵌套 iframe 参照误判为已关闭，同时继续排除背景页面与已关闭旧弹层。
- 收紧 `first_available` 根回填判定：目标根仅显示“请选择”等空态占位文本时，不得作为真实回填证据参与 `target-backfill` 早退。
- 保持自动关闭且目标单元格真实回填的既有成功路径，不改变候选选择、确认按钮点击或 DSL schema。
- 增加聚焦回归测试，覆盖“dialog 外壳只含 iframe、实际候选面在子 frame、子 frame URL 与标题不含参照关键字”的真实形态。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `popup-reference-tree-table-selection`: 补充嵌套 iframe 外壳形态下参照弹窗关闭判定要求，明确候选面位于 dialog 所包含的子 frame 时不得因 URL/标题关键字不匹配而误判关闭。
- `editable-table-cell-entry`: 补充 `first_available` 弹出参照根回填判定要求，明确“请选择”等空态占位文本不得单独证明字段已回填。

## Impact

- 影响 `ydf_browser/runtime.py` 的共享弹出参照关闭判定、跨 frame 候选面扫描和可编辑表格根回填判定。
- 增加 `tests/test_runtime.py` 聚焦回归，覆盖嵌套 iframe 外壳、空态占位文本和既有自动关闭成功路径。
- 真实验收使用 `流程-单位资金分散-批量支付-正向流程（审核）-001` 的 `batch_payment_apply_decentral` 用例，以及同类 `流程-预算执行-预算拨款-外贷拨款申请流程-外贷提款-0001` 用例。
- 不改变 DSL schema、解析器、外部依赖和普通下拉选择语义。
