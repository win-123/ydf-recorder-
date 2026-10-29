## Why

`明细指标管理` 用例通过 `table_row_selection.select` 在树形表格中按复合条件选择业务行时，目标行真实存在但默认折叠，运行时却报“未找到可选择的表格行”。现有展开逻辑把第一个匹配值误当作树祖先编码提示，且展开过程未限定到 executor 已解析的目标表格，导致复合条件顺序影响结果并可能遍历错误表格。

## What Changes

- 修正树形表格行选择的展开作用域，使查找、展开、滚动和命中判断始终限定在 `target.table` / `table_fieldid` 解析出的目标表格内。
- 让 `target.match.conditions` 的 AND 语义与条件顺序无关，不再从任意第一个业务条件错误推导树祖先路径。
- 复用现有逐节点展开能力；只有能够确认目标值属于树形列且编码关系有效时才使用前缀优化，否则执行目标表内通用遍历。
- 为成功和失败路径保留树表查找诊断，记录展开、滚动、耗时、目标表格和匹配条件。
- 增加复合条件、条件换序、目标表作用域和真实折叠子行的回归验证。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `table-row-selection`: 补充树形表格中折叠业务行的目标表内展开、复合条件顺序无关及诊断要求。

## Impact

- 主要影响 `ydf_browser/runtime.py` 的树表展开和表格行选择路径，以及 `ydf_browser/executor.py` 的步骤结果诊断传递。
- 更新 `tests/test_runtime.py`、`tests/test_executor.py` 和相关真实 YAML 验证。
- 不新增 DSL 字段，不改变普通平面表格、行号选择、全选和表格行级动作的既有语义，不增加外部依赖。
