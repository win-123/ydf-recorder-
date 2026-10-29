## Why

真实 DSL 在 `editable_table.fill_row` 为 `收款人信息.收款人全称` 执行 `first_available: true` 时，运行时已勾选候选行，却把仍可见的 iframe 弹出参照误判为已关闭，并在目标单元格仍显示“请选择”时提前返回，最终导致字段未回填。现有规格分别覆盖 iframe 参照确认和可编辑表格回填，但尚未明确“候选产生临时内部值、目标单元格仍未回填、iframe 候选层仍可见”的组合状态。

## What Changes

- 明确可编辑表格弹出参照只有在候选层真实关闭且目标单元格真实回填时，才能通过 `target-backfill` 路径提前结束。
- 当 iframe 候选层仍包含业务候选和 `确定/确认/保存` 动作时，运行时继续执行当前参照内的确认动作并等待目标单元格回填。
- 修复共享弹出参照关闭判定，避免临时内部值或失效的旧 locator 把仍可见的当前参照误判为已关闭。
- 增加针对 `PAYEE_ACCOUNT_MANAGE_SELECT` 形态的回归测试，并使用原始真实 DSL 验证第 7 步能够完成。
- 不新增 DSL 字段，不改变 `first_available` 的候选选择语义，也不放宽未回填时的失败条件。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `editable-table-cell-entry`: 补充 iframe 式可编辑表格参照在候选已选中但目标单元格尚未回填时不得提前结束、必须继续确认的要求。

## Impact

- 影响 `ydf_browser/runtime.py` 中共享弹出参照关闭判定、可编辑表格参照确认和回填收口路径。
- 增加 `tests/test_runtime.py` 聚焦回归，覆盖仍可见 iframe 参照、临时内部值和目标单元格占位文本的组合状态。
- 真实验收使用 `/Users/ken/temp/ydf-browser-问题反馈/流程-单位资金分散-批量支付-正向流程（审核）-001.yaml` 的 `batch_payment_apply_decentral` 用例。
- 不影响 DSL schema、解析器、外部依赖和普通下拉选择语义。
