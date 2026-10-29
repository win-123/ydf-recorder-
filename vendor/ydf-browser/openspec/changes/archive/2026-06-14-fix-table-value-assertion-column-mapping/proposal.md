## Why

`项目预算>>项目预算管理>>项目授权` 的 YDF-80492 用例最终需要验证授权明细中 `被授权人名称 = 人员二十二` 这一行的 `可授权金额 = 400.00`。当前 `table.assert_column_values` 和 `table.assert_row_values` 在该页面会把 `可授权金额` 串到 `起始时间` 或 `项目名称` 等相邻/错误列，导致真实页面已有目标列和目标值时仍断言失败。

这个问题暴露出表格数据值断言没有复用 `table.assert_columns` 已具备的目标表格作用域、表头归一化和列身份定位能力，在多列、固定列、分离 header/body 或动态授权页模板中容易串列。

## What Changes

- 修复 `table.assert_column_values` 的列值采集，使其限定在解析出的目标表格作用域内，并按真实表头/列身份定位目标列，不能全页面裸扫后误采其它列。
- 修复 `table.assert_row_values` 的行字段采集，使其先按 `target.match` 找到目标业务行，再按同一目标表格内的列映射读取字段值。
- 当页面存在多张可见主表格且 DSL 未明确表格、也无法唯一解析目标表格时，数据值断言应像 `table.assert_columns` 一样拒绝歧义，而不是返回错误列数据。
- 失败诊断需要包含目标列、匹配行、可用 headers、解析到的 table/table_fieldid 等信息，帮助判断是用例写法问题还是页面数据问题。
- 最终验证时同步修正 `/Users/ken/temp/ydf-browser-问题反馈/特性-项目管理-项目预算-YDF-80492-YDFJF-1950-0001 (1).yaml`：断言应放在 `保存` 后，使用 `被授权人名称 = 人员二十二` 定位行，再断言该行 `可授权金额 = 400.00`。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `table-column-assertions`: 扩展表格断言能力，要求表格数据值断言与表头列集合断言使用一致的表格作用域、列定位和失败诊断语义。

## Impact

- 主要影响 `ydf_browser/executor.py` 和 `ydf_browser/runtime.py` 中的表格列值/行值采集链路。
- 需要补充或调整 `tests/test_executor.py`、`tests/test_runtime.py` 中关于 `table.assert_column_values`、`table.assert_row_values`、多表格歧义、固定列/相邻列串列的回归测试。
- 需要更新目标真实 YAML 用例并用源码入口真实执行，确认 `被授权人名称 = 人员二十二` 行的 `可授权金额 = 400.00` 可以通过。
- 不引入新外部依赖，不改变 `table.assert_columns` 已有表头集合断言语义。
