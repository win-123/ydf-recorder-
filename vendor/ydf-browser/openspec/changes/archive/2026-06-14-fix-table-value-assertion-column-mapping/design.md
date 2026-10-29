## Context

当前 `table.assert_columns` 已经具备比较完整的表格作用域解析：executor 能解析 `target.table`、唯一可见主表格和模板列清单，runtime 的 `collect_table_headers()` 也能在指定 table/table_fieldid 作用域内采集表头并横向滚动。

但 `table.assert_column_values` 和 `table.assert_row_values` 仍主要依赖全页面 DOM 脚本。`collect_table_column_values(column)` 只传列名，不传表格作用域或模板列清单；`collect_table_row_values(match, columns)` 也只把匹配值和字段列名交给页面脚本。真实 YDF-80492 用例中，点击 `授权` 后模板表头包含 `可授权金额`，但值断言会把该列串到 `起始时间` 或 `项目名称`，说明 header/body 对齐、固定列副本或错误表格根选择存在问题。

用户的最终业务验证不是“整列所有可授权金额都等于 400.00”，而是“保存授权后，`被授权人名称 = 人员二十二` 这一行的 `可授权金额 = 400.00`”。因此用例应改成 `table.assert_row_values`，程序则需要让行值断言能可靠读取目标行目标列。

## Goals / Non-Goals

**Goals:**

- 让 `table.assert_column_values` 和 `table.assert_row_values` 复用与 `table.assert_columns` 一致的表格作用域解析。
- 让 runtime 在目标表格内按真实表头、列 identity 和 header/body 关系读取单元格值，避免相邻列、固定列副本或其它表格串列。
- 让行值断言能先用 `target.match` 定位业务行，再读取同一行中的目标字段列。
- 支持在数据值断言中显式或推断目标表格；无法唯一解析时给出清晰失败，而不是返回错误列数据。
- 修正 YDF-80492 YAML，使最终验证使用 `被授权人名称 = 人员二十二` 定位行并断言 `可授权金额 = 400.00`。

**Non-Goals:**

- 不改变 `table.assert_columns` 的表头集合断言行为。
- 不把 `table.assert_column_values` 改成“任意一行匹配”语义；它仍表示目标列采集到的所有值都满足预期。
- 不为 YDF-80492 的 fieldid、dataField 或菜单写页面专用硬编码。
- 不引入 Playwright 之外的新依赖。

## Decisions

1. 数据值断言先在 executor 层解析表格上下文。

   `_execute_table_assert_column_values()` 和 `_execute_table_assert_row_values()` 应像 `_execute_table_assert_columns()` 一样解析 `target.table` / `target.table_name`，并在未显式指定时尝试根据目标列集合推断唯一表格。行断言的推断列集合包括 `target.match` 中的列和 `target.fields` 中的列，例如 `被授权人名称` + `可授权金额`。

   替代方案是继续让 runtime 全页面搜索并尝试更复杂的几何判断。这个方案仍缺少模板上下文，遇到多个表格、固定列副本和隐藏表格时诊断较差。

2. runtime 值采集接口接收 table/table_fieldid/table_columns。

   扩展 `collect_table_column_values()` 和 `collect_table_row_values()` 的可选参数，保持旧 FakeRuntime/测试对象兼容：executor 通过签名检查只向支持参数的 runtime 传递新上下文。真实 Playwright runtime 使用 `_table_selection_context()` 获取目标表格根，并复用 `collect_table_headers()` 的表头采集/滚动策略。

   替代方案是新增完全独立方法名，风险是 executor 分支更散，旧断言路径继续存在并可能被误用。

3. 单元格定位以列身份优先，索引和几何兜底。

   采集脚本应优先使用 header/cell 的 `data-field`、`data-index`、`data-key`、`data-column-key`、`fieldid`、模板列候选中的 `data_field` / `fieldid` 等 identity 对齐；只有缺少 identity 时才使用同一 header row 的列索引和同一 table root 的 body row。几何对齐只能作为最后兜底，并必须限定在目标表格根内。

   这样可以覆盖 WUI header/body 分离、固定列复制和横向滚动场景，也能避免 `可授权金额` 被读成 `起始时间` 或 `项目名称`。

4. 行断言使用业务行匹配后再取同一行字段。

   `table.assert_row_values` 应先在目标表格范围内找到包含 match 条件的业务行。`match.conditions` 多条件时，运行时应按每个条件列读取同一行的值来判断，而不是只做整行文本包含。找到目标行后，再用同一套列定位读取 `fields` 中的每个列值。

   对 YDF-80492，最终 YAML 应表达为：保存后按 `被授权人名称 = 人员二十二` 定位授权明细行，再断言 `可授权金额 = 400.00`。

5. 失败诊断返回上下文而不是误采值。

   当目标列不存在、目标表格不唯一、目标行找不到或单元格无法定位时，错误信息应包含目标列/匹配条件、解析出的 table/table_fieldid、采集到的 headers，以及必要时的候选表格列表。不要把其它列的值当作目标列 mismatches。

## Risks / Trade-offs

- [Risk] 旧用例依赖全页面裸扫描偶然通过。-> Mitigation: 数据值断言只在可确定目标表格时继续执行；无法确定时失败并提示补充 `target.table` 或更具体的 match 条件。
- [Risk] 真实 YonDiF 表格 DOM 变体多，identity 属性不总是齐全。-> Mitigation: 按 identity、列索引、目标表格内几何对齐分层兜底，并用现有 `table.assert_columns` 表头采集作为基础。
- [Risk] 横向滚动读取目标列可能改变页面滚动位置，影响后续步骤。-> Mitigation: 与现有表头采集一样只在表格滚动容器内滚动；验证后不要求恢复滚动位置，后续步骤应按语义重新定位。
- [Risk] 多表格页面仅靠列集合推断仍可能有多个候选。-> Mitigation: 这种情况应显式失败，不返回任意第一张表的值。

## Migration Plan

- 这是 DSL 向后兼容修复。已有 `table.assert_column_values` 和 `table.assert_row_values` 写法继续有效。
- 新增可选 `target.table` / `target.table_name` 支持，用于数据值断言需要显式限定表格时。
- 修正 YDF-80492 临时用例文件，最终真实验证命令使用源码入口 `./.venv/bin/python -m ydf_browser.cli run --dsl ... --headless --report-file ...`。

## Open Questions

- 无待确认问题；当前用户已明确最终验证目标是 `被授权人名称 = 人员二十二` 行的 `可授权金额 = 400.00`。
