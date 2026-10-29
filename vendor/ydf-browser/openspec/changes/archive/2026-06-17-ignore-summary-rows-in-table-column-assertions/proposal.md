## Why

`table.assert_column_values` 在执行项目立项列表中会把表格末尾的 `小计/合计` 行当作普通业务行采集，导致查询结果里业务行均匹配时仍因汇总金额值失败。真实复现中 `项目名称 = ui自动化wdy0033` 的断言额外采到 `190,000.00`，该值来自末尾 `tfoot-tr ... bsubtotal` 小计行。

## What Changes

- `table.assert_column_values` 的列值采集 MUST 排除 WUI/Ant/Element 等表格中的汇总、页脚、小计、合计、总计行。
- 汇总行过滤规则应覆盖 class 标识和文本标识，避免 `tfoot-tr`、`subtotal`、`summary/footer/total`、首单元格或整行文本为 `小计/合计/汇总/总计` 的行进入断言值集合。
- 保持普通业务行、固定列副本、header/body 分离表格的现有列映射能力不变。
- 不改变 DSL 语法；现有 `table.assert_column_values` 用例无需新增参数。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `table-column-assertions`: 表格列值断言的运行时采集规则增加汇总行排除要求。

## Impact

- 影响 `ydf_browser/runtime.py` 中 `collect_table_column_values` 使用的列值采集脚本。
- 需要补充针对 `table.assert_column_values` 的单元回归，覆盖 `tfoot-tr/bsubtotal`、`小计/合计` 等汇总行。
- 需要用真实 YAML `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-项目库-YDF-82797-0001-执行项目新增父子项目和设置经费管理员.yaml` 验证第一个 `table.assert_column_values` 不再采集 `190,000.00`。
