## Why

`editable_table.fill_row` 录入 `YDFTreeModalSelect` 银行网点时，运行时向参照过滤框写入标量值后立即按候选唯一性判断，但部分平台参照必须点击搜索图标或按回车才会真正过滤，导致未过滤的 15 条候选被误报为歧义。现有标量参照规格已经要求“隐式过滤后唯一选择”，需要补齐不同页面过滤触发方式的兼容行为。

## What Changes

- 为标量弹出参照的隐式过滤增加受控提交重试：首次候选仍有歧义时，主动使用现有搜索图标/回车提交过滤，再重新解析候选。
- 当过滤结果包含层级节点和叶子节点时，完整标量值命中单个候选后优先选择该精确候选。
- 提交后仍有多个不同业务候选时，继续失败并保留数量、候选摘要及明确选择建议；不得默认选择第一条。
- 保留已有自动过滤页面的快速路径，显式 `filter`、`match`、`first_available`、`row_number`、`selections` 等语义不变。
- 增加运行时回归测试，并用资金往来对象真实 DSL 验证银行网点字段能够继续录入。
- 不新增 DSL 字段，不添加银行网点页面特例，不强制所有参照在输入后重复查询。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `popup-reference-tree-table-selection`: 明确标量隐式过滤在首次候选仍未收敛时必须提交过滤并重试，最终仍遵守唯一候选约束。
- `editable-table-cell-entry`: 明确可编辑表格参照列复用同一标量过滤提交重试语义。

## Impact

- 运行时：`ydf_browser/runtime.py` 的共享弹出参照选择路径。
- 测试：`tests/test_runtime.py`，覆盖自动过滤、提交后收敛、提交后仍歧义三类路径。
- OpenSpec：更新两个现有能力的 delta spec。
- 真实验证：`/Users/ken/temp/ydf-browser-问题反馈/fund_counterpart_basic_maintenance.yaml` 的 `editable_table.fill_row` 银行网点步骤，以及该用例后续独立业务结果。
