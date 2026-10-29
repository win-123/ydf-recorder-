## Why

`editable_table.add_row` 当前同时依赖模板表格名预检和运行时 DOM 可见标题匹配，但真实页面可能出现分组标题、模板表格名、运行时表头文本不一致的情况。`流程-收入预算执行-非税收入缴库全景-001.yaml` 在 `缴款明细信息` 分组下新增明细行时，执行器先因模板名不匹配拦截；改成模板名 `缴库明细表格` 后，运行时又因 DOM 附近只暴露表头列名而拒绝点击。

## What Changes

- 让 `editable_table.add_row` 使用与 `editable_table.fill_row` 一致的目标表格身份解析，支持 DSL 写页面分组标题或模板表格名时定位同一个可编辑表格。
- 将解析出的表格身份传给运行时新增行逻辑，避免只靠页面可见文本判断表格归属。
- 新增行点击后校验目标表格中真实出现可编辑数据行；如果仍是 `暂无数据` 或未增加行，应失败并输出诊断，而不是报告“已新增行”。
- 保持未指定 `target.table` 的既有行为：页面只有一个明确新增入口时仍可直接点击。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `editable-table-cell-entry`: 扩展可编辑表格新增行与后续单元格录入的目标表格作用域契约，确保两者使用一致的表格身份和失败诊断。

## Impact

- 影响 `ydf_browser/executor.py` 中 `editable_table.add_row` 的表格名解析、预检和传参。
- 影响 `ydf_browser/runtime.py` 中 `_EDITABLE_TABLE_ADD_ROW_SCRIPT` 或其调用包装的表格 root 匹配、点击后结果校验和诊断。
- 需要补充最小单元回归，覆盖页面分组标题与模板表格名不一致、运行时无可见表格标题、点击后仍为空态三类情况。
- 需要用原始问题用例或等价临时 YAML 在真实 YonDiF 页面验证增行能进入可编辑行。
