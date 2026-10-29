## Why

`editable_table.fill_row` 在“指标信息调剂表”的 `单位内部机构` 列上失败：运行报告和追加诊断都显示运行时已命中目标表格、目标行和目标单元格，但多轮自动化激活后仍未出现输入控件或候选层。人工点击同一单元格可以进入编辑态并弹出参照，说明问题不在 DSL 字段语义或表格定位，而在可编辑表格单元格激活策略没有稳定模拟真实用户点击。

## What Changes

- 增强可编辑表格单元格激活逻辑：在命中目标单元格后，应优先找到能够触发编辑态的真实点击点，而不是只对单元格容器做固定点位 click / dblclick / JS dispatch。
- 在点击尝试之间识别可编辑态成功信号，包括单元格内编辑器、全页面前景候选层、焦点输入控件或目标单元格状态变化。
- 对 `YDFInput disabled=1` 但人工点击可编辑的表格列提供兼容：模板 `disabled` 不能被直接解释为运行时不可编辑。
- 增强失败诊断，区分“命中正确单元格但未进入编辑态”、“被行级动作或浮层遮挡”、“候选层已出现但未被识别”和“真实不可编辑列”。
- 不引入 DSL 破坏性变更；既有普通文本、数字、choice、弹出参照、结构化参照和多表格列身份定位语义保持兼容。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `editable-table-cell-entry`: 修复可编辑表格单元格已正确定位但自动化点击无法进入编辑态的问题，并补充激活诊断要求。

## Impact

- 主要影响 `ydf_browser/runtime.py` 中 `_activate_editable_table_cell`、点击点选择、编辑态等待和失败诊断相关逻辑。
- 可能需要补充单元测试或 fixture 测试，覆盖可编辑表格单元格容器与真实编辑触发区域不一致、hover 后行级动作覆盖、`YDFInput disabled=1` 但点击可编辑等场景。
- 真实浏览器回归用例：`/Users/ken/temp/ydf-browser-问题反馈/流程-预算管理-调整调剂_财务-明细指标管理-分配正向-002new.yaml`，关注第 7 步 `editable_table.fill_row` 的 `单位内部机构` 字段。
- 不增加外部依赖，不改变 CLI 参数和 DSL 结构。
