## Why

`流程-预算管理-项目库-二级项目管理财务-新增-0001` 真实执行时整体报告 `passed`，但 `项目联系人` 和 `项目负责人` 两个人员弹出参照字段只记录了 `selected`，结果仍为 `confirmed=false`，实际前景参照没有正常关闭。

这会让 `form.fill` 出现绿灯假阳性：候选可能被点过，但字段选择没有完成确认，后续步骤在错误的前景层或半完成状态中继续执行。

## What Changes

- 收紧普通 `form.fill` 弹出参照字段的成功条件：结构化参照选择不能以 `confirmed=false` 报告字段录入成功。
- 保留可编辑表格参照的既有回填兜底，但该兜底必须限定在有外层单元格回填校验的路径中，不能泛化到普通表单字段。
- 弹出参照早退逻辑必须区分“候选点击后字段已真实回填且候选层关闭”和“候选选择未确认但被误判为可继续”。
- 步骤结果需要保留足够诊断信息，例如 `confirmed`、`confirm_label`、`close_action`、字段回填状态或前景参照状态，便于定位绿灯假阳性。
- 不新增 DSL 字段，不改变 `filter + match` 的 YAML 写法。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `popup-reference-tree-table-selection`: 补充 `form.fill` 中普通表单弹出参照字段的确认/关闭成功条件，并限定候选点击后的早退规则。

## Impact

- 影响 `ydf_browser/runtime.py` 的弹出参照选择、确认、关闭判断和早退逻辑。
- 影响 `ydf_browser/executor.py` 对 `form.fill` 字段级参照结果的成功判定和报告。
- 需要补充 `tests/test_runtime.py` / `tests/test_executor.py` 中覆盖 `selected` 但 `confirmed=false` 不得让普通表单字段成功的回归。
- 需要用真实 YAML `/Users/ken/temp/ydf-browser-问题反馈/流程-预算管理-项目库-二级项目管理财务-新增-0001.yaml` 验证人员参照字段能正常确认关闭，或在不能确认关闭时失败。
