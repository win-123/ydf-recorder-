## Why

`实物管理-易耗品物资-领用申请-待提交页签新增-0005.yaml` 在连续运行时出现一次成功、一次失败：第一次保存出的待提交列表行在第二次运行中进入 DOM 候选，导致 `editable_table.fill_row` 的 `申请数量` 定位串到背景列表行，而不是当前新增页的 `物资信息` 子表行。

这不是基础数据缺失问题，而是可编辑表格单元格定位没有稳定限定到前景目标表格；随着测试数据积累，同一用例会从稳定通过变成不稳定失败。

## What Changes

- 强化 `editable_table.fill_row` 的目标表格作用域：有 `target.table`、模板 `table_fieldid` 或列所属区域时，单元格搜索必须优先限定到当前前景可操作的对应表格根。
- 对 `row_number: -1` 的语义收紧到目标表格内的最后一条可编辑数据行，不能在全页可见行集合中取最后一行。
- 排除背景列表、被前景新增页遮挡的表格、旧模板残留表格、业务助手 iframe 和非目标表格行。
- 增强失败诊断，记录命中的表格根、行文本、行来源、前景层判断和目标表格身份，便于区分程序串表与业务数据不存在。
- 增加针对连续运行后列表已有数据的回归覆盖，并用真实 YAML 验证稳定性。

## Capabilities

### New Capabilities

暂无。

### Modified Capabilities

- `editable-table-cell-entry`: 可编辑表格单元格定位新增前景目标表格隔离要求，避免背景列表数据影响 `fill_row`。

## Impact

- 主要影响 `ydf_browser/runtime.py` 中可编辑表格单元格搜索、激活和诊断逻辑。
- 可能涉及 `ydf_browser/executor.py` 传递更完整的目标表格/列区域身份。
- 需要新增或调整 `tests/test_runtime.py`、`tests/test_executor.py` 中可编辑表格定位回归。
- 真实验证用例为 `/Users/ken/temp/ydf-browser-问题反馈/实物管理-易耗品物资-领用申请-待提交页签新增-0005.yaml`，重点复核连续运行时不会串到上一轮保存的待提交列表行。
