## Why

真实用例 `流程-预算管理-调整调剂_财政-待分配预算管理（预算部门）逆向-001.yaml` 在 `editable_table.add_row target.table=调入方` 时失败。页面初始为空表格，点击 placeholder 新增入口后实际生成了行，但运行时把同一 placeholder 新增入口重试点击了一次，最终报告 `before_rows=2; after_rows=2; retry_count=1`，导致空表格首次新增被误判为未生效。

现有规格已经要求新增后验证真实数据行，也允许非空表格首次点击未增长时受控重试；缺口是没有明确空目标表格 placeholder 首次新增成功时不得进入重试，以及 placeholder 按钮本身不能作为不可靠的行数验证根。

## What Changes

- 修正 `editable_table.add_row` 对空目标表格 placeholder 新增入口的成功判定：点击前为空、点击后目标表格出现第一条真实可编辑行时必须成功。
- 收紧重试边界：只有点击前目标表格 root 已可靠确认存在真实数据行，且点击后未增长时，才允许一次受控重试。
- 要求目标验证 root 不能停留在 `.ydf-table-placeholder-add-button` 等新增按钮自身，必须回到目标表格 fieldid、目标列身份或同一表格 cluster 对应的 root。
- 保留既有失败门禁：目标表格仍为空、无法唯一确认目标 root、或非空表格点击后行数未增长时仍失败。
- 增加失败诊断要求，保留首次点击和最终点击的目标表格身份、候选入口、点击前后行状态，便于区分真实未新增和误触发重试。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `editable-table-cell-entry`: 修改 `editable_table.add_row` 的空表格 placeholder 新增成功判定、目标验证 root 约束和受控重试条件。

## Impact

- 影响代码：`ydf_browser/runtime.py` 中 `PlaywrightRuntime.add_editable_table_row`、`_EDITABLE_TABLE_ADD_ROW_SCRIPT`、`_editable_table_add_row_should_retry` 及相关诊断格式。
- 影响测试：补充 runtime 聚焦测试，覆盖空目标表格 placeholder 首次新增成功、placeholder root 不作为验证 root、非空表格未增长仍可受控重试、目标 root 不可靠时失败。
- 影响验证：需要重跑本次预算管理真实 DSL，证明 step 7 不再因 placeholder 新增误判失败，并按变更范围运行相关 pytest。
