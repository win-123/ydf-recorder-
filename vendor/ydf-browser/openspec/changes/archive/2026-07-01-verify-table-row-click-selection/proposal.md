## Why

`流程-预算管理-调整调剂_财政-待分配预算管理（预算部门）-分配正向-002.yaml` 中，`调出方` 表格没有 checkbox。`table_row_selection.select target.table=调出方 target.row_number=1` 当前被报告为成功，但后续 `调入方` 增行/录入收到业务提示 `请选择一条调出方数据数据`，说明行点击没有真实建立表格选中状态。

## What Changes

- 收紧 `table_row_selection.select` 的无 checkbox 行点击语义：点击动作发出不等于选择成功，runtime 必须在点击后确认目标行或目标表格出现真实选中/当前行证据。
- 覆盖按 `target.row_number`、`target.first_available` 和按匹配条件定位目标行后走行点击 fallback 的路径。
- 失败诊断必须能区分“目标行不存在”“目标行存在但无可用选择控件”“已点击业务行但没有选中证据”。
- 步骤报告补充可审计的行点击诊断，便于后续从报告直接判断 checkbox 路径还是 row-click 路径。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `table-row-selection`: 表格行选择在无 checkbox 行点击 fallback 中必须验证真实选中态，不能仅以 Playwright click 成功作为步骤成功。

## Impact

- 影响 `ydf_browser/runtime.py` 中表格行选择的无 checkbox 行点击 fallback。
- 影响 `ydf_browser/executor.py` 中 `table_row_selection.select` 的步骤报告数据。
- 需要更新 `openspec/specs/table-row-selection` 的 delta spec，清理既有冲突表述。
- 需要补充 runtime/executor 回归测试，并用本次真实 YAML 验证第 6 步不再假成功，最终链路能进入 `调入方` 录入。
