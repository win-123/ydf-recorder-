## Why

`监督检查方案1.yaml` 在“检查分工”页面添加内部检查小组成员后，页面已经出现 `财会监督1` 成员行，但 `table_row_selection.select` 仍报“未找到可选择的表格行”。该页面使用嵌套 WUI 表格，且表头与表体分离渲染；当前表格作用域解析会导致已存在的目标行无法被选择或断言读取。

## What Changes

- 修复指定 `target.table` 或解析出的 `table_fieldid` 后，嵌套 WUI 表格 header/body 分离时的数据行定位。
- 让 `table_row_selection.select` 能在 `内部检查小组` 这类嵌套子表中按列值找到目标行并勾选 checkbox。
- 让 `table.assert_column_values` / `table.assert_row_values` 在同类表格中用同一个表格作用域关联 header 与 body，不因 header root 不包含 body 而返回空值。
- 增强失败诊断，输出实际解析到的表格根、目标表头、可见行文本和选择器统计，便于区分 DSL 写法、数据缺失和 runtime 解析缺陷。
- 不改变 DSL 语法；原始反馈用例将同步改为显式表格和真实列名写法。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `table-row-selection`: 指定表格作用域时，嵌套 WUI 表格即使 header/body 分离也必须能定位并勾选目标业务行。
- `table-column-assertions`: 数据值断言在嵌套 WUI 表格中必须正确关联 header/body 并读取目标列值。

## Impact

- 主要影响 `ydf_browser/runtime.py` 的表格作用域解析、行选择和列值采集脚本。
- 可能补充 `ydf_browser/executor.py` 的错误诊断数据，但不改变现有 DSL 输入结构。
- 需要新增针对 WUI 分离表头/表体、嵌套多表页面的单元测试，并用 `/Users/ken/temp/ydf-browser-问题反馈/监督检查方案1.yaml` 或等价诊断用例做真实运行验证。
