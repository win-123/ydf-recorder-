## Why

费用明细新增会连续打开项目、指标和费用参照。当前默认确认把被下一参照覆盖的旧参照误判为未关闭；全部参照确认后，模板上下文仍停留在临时参照，无法按“费用明细”录入金额。

## What Changes

- 共享参照完成判定识别确认后前景选择面已切换的情况，同时保留同一参照仍活跃时的失败判定。
- 连续参照选择及时应用新模板，在最后确认后恢复已重新可操作的父表单。
- 增加真实浏览器失败测试、模板恢复边界测试和不保存、不提交的最小真实 DSL。
- 更新参照 DSL 使用说明，不增加字段或依赖。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `popup-reference-tree-table-selection`：确认后可连续进入下一参照，旧参照后台保留不阻塞已完成的选择。
- `dynamic-template-context-restoration`：连续临时参照结束后恢复可操作的父表单，保留仍活跃的中间选择面。

## Impact

涉及 `ydf_browser/popup_reference/` 的共享完成判定、`ydf_browser/template_restoration.py`、相邻入口回归、真实 DSL 和使用文档；不改业务页面，不保存或提交业务单据。
