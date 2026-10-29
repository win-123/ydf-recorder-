## Why

真实用例 `/Users/ken/temp/ydf-browser-问题反馈/14功能-预算执行-采购管理-采购需求编制-新增提交-0001.yaml` 在 `需求清单` 执行 `editable_table.add_row` 后，页面仍只显示空态和 `+ 新增`，但报告将该步骤标记为成功，并把失败延迟到后续 `editable_table.fill_row` 的 `采购品目` 参照列。当前运行时把非目标表格的已有行纳入新增成功判定，导致报告定位与界面事实不一致。

## What Changes

- 收紧 `editable_table.add_row` 的目标表格验证：点击后必须证明解析出的目标表格出现真实可编辑数据行，不能用同一大容器里的其他表格行作为成功证据。
- 当目标表格仍为空态、仍显示 `暂无数据`，或没有可供后续 `editable_table.fill_row` 定位的行时，让 `editable_table.add_row` 当前步骤失败并输出诊断。
- 保持 DSL 语法不变，不新增坐标、等待或页面专用配置。

## Capabilities

### New Capabilities

### Modified Capabilities
- `editable-table-cell-entry`: 强化 `editable_table.add_row` 成功判定，要求新增行验证限定在目标表格身份和目标运行时 root 内。

## Impact

- 影响 `ydf_browser/runtime.py` 中 `_EDITABLE_TABLE_ADD_ROW_SCRIPT` 的目标表格 root 选择、点击后验证和诊断输出。
- 影响 `tests/test_runtime.py` 中可编辑表格新增行的回归覆盖。
- 需要真实验证问题 YAML，确认失败归因回到 `editable_table.add_row`，修复后能在 `需求清单` 产生可编辑数据行并进入后续录入链路。
