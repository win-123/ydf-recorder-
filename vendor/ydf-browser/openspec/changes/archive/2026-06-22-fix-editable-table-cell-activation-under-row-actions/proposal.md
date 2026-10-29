## Why

真实用例 `/Users/ken/temp/ydf-browser-问题反馈/功能-预算管理-项目库（高校）-收入项目管理-储备项目-复制新增-0001.yaml` 在 `测算信息` 可编辑表格录入 `测算依据及说明` 时失败。前两个数字列已成功录入并触发测算数联动，但目标文本列被行级动作浮层覆盖，运行时激活单元格后没有出现输入控件。

## What Changes

- 让 `editable_table.fill_row` 在目标单元格被行级 `插入`、`复制`、`删除`、更多按钮等浮层覆盖时，仍能避开动作按钮并激活真实单元格编辑器。
- 在无法激活编辑器时保留现有失败语义，并让诊断能体现表格、行、列和遮挡现场。
- 保持现有 DSL 语法不变，不新增等待、坐标或低层点击写法。

## Capabilities

### New Capabilities

### Modified Capabilities
- `editable-table-cell-entry`: 补充可编辑表格单元格激活要求，覆盖行级动作浮层遮挡目标编辑区域的场景。

## Impact

- 影响 `ydf_browser/runtime.py` 中可编辑表格单元格激活和点击点选择逻辑。
- 影响 `tests/test_runtime.py` 中可编辑表格单元格激活回归测试。
- 需要真实验证问题 YAML，确认能越过 `测算依据及说明` 录入并继续保存链路。
