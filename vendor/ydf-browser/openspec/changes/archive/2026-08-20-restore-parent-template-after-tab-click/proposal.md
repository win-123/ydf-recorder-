## Why

动态新增表单保存后点击父列表页签时，运行时 DOM 已切回列表，但 executor 仍可能保留包含主表格的子 manifest，导致后续 `table_row_selection.select` 用子表格身份扫描列表并全部得到 `not-found`。现有恢复逻辑只判断子 manifest 是否声明主表格，无法识别这些表格已经退出活动工作面。

## What Changes

- 在 `tab.click` 完成后根据当前与父 manifest 的运行时可见性证据决定是否恢复父模板。
- 当前动态模板仍暴露前景稳定动作或可编辑字段时继续保留当前模板，不因背景父列表可扫描而恢复。
- 为“子 manifest 自带主表格、页签切回父列表、随后选择列表行”增加回归覆盖。
- 保持 `table_row_selection.select` 的表格名称、列匹配、歧义和 `not-found` 语义不变。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `dynamic-template-context-restoration`: 补充 `tab.click` 实际切回父列表后的模板恢复要求，以及当前动态模板仍活跃时的保留边界。

## Impact

- 代码：`ydf_browser/executor.py` 的页签点击后模板恢复路径。
- 测试：`tests/test_executor.py` 的动态模板、页签与表格选择组合回归。
- 规格：`dynamic-template-context-restoration` delta spec。
- DSL、schema、依赖和公开命令均不变。
