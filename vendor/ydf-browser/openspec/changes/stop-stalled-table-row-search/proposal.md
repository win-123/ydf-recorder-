## Why

`table_row_selection.select` 在目标行不存在时会对同一个点击后没有产生任何行变化的疑似树表展开候选持续重试，真实报告中因此额外等待约 88 秒。需要让搜索在候选无进展时及时跳过，同时保留真实树表展开和普通表格滚动查找能力。

## What Changes

- 限制同一树表展开候选在没有产生行变化时的重试次数，达到上限后跳过该候选。
- 继续查找其它未尝试候选并保留表格纵向滚动，不因单个无效候选阻塞整次行搜索。
- 保留 `row_search` 诊断以及真实树表展开成功后的既有行为。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `table-row-selection`: 增加表格行搜索对无进展树展开候选的有限重试和继续搜索要求。

## Impact

- 运行时：`ydf_browser/runtime.py` 的表格行搜索循环。
- 测试：`tests/test_runtime.py` 的树表展开重试与无进展终止覆盖。
- DSL、schema、依赖和命令行接口不变。
