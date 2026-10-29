## 1. Reproduction And Test Coverage

- [x] 1.1 用现有 `/Users/ken/temp/ydf-browser-问题反馈/监督检查方案1.yaml` 或等价 `/tmp` 诊断 YAML 复现 `内部检查小组` 表格中目标成员行存在但 `table_row_selection.select` 失败的问题，并记录报告路径。报告：`/tmp/ydf-supervision-plan1-precise-before-fix-report.json`
- [x] 1.2 为 header/body 分离的嵌套 WUI 表格新增 runtime 单元测试，覆盖 `table_row_selection.select target.table=内部检查小组` 能按 `人员名称=财会监督1` 勾选目标行。
- [x] 1.3 为同一 DOM 结构新增 `table.assert_column_values` 或底层 `collect_table_column_values` 单元测试，覆盖指定 `table_fieldid=2_2_tab` 时能读取 `人员名称` 列值。
- [x] 1.4 为 `table.assert_row_values` 或底层 `collect_table_row_values` 补充同一表格簇的行值读取测试，避免后续只修列值断言。

## 2. Runtime Implementation

- [x] 2.1 调整表格 fieldid/name root 解析逻辑，使 WUI 分离表头/表体时返回或构建能关联同一业务表格 header 和 body 的作用域。
- [x] 2.2 调整行选择路径，确保 `_click_row_checkbox_by_match_values` 在指定 `table` / `table_fieldid` 时能在关联 body 中找到目标行并点击 checkbox。
- [x] 2.3 调整列值和行值采集脚本，优先用 identity 对齐 header/body 单元格，缺少 identity 时在目标表格簇内使用列索引或几何对齐兜底。
- [x] 2.4 增强失败诊断，至少包含 `table`、`table_fieldid`、目标列、匹配值、解析根摘要、headers、可见 rows 或选择器统计。

## 3. Real Case Verification

- [x] 3.1 将反馈 YAML 使用推荐写法运行：`table: 内部检查小组`、`column: 人员名称`、`equals: 财会监督1`。
- [x] 3.2 验证修复后该用例能越过成员行选择并执行后续 `保存`；当前数据缺少外部检查人员，已用 `notification.assert` 明确断言预期业务错误。报告：`/tmp/ydf-supervision-plan1-original-updated-after-fix-report.json`
- [x] 3.3 运行 `openspec validate support-nested-wui-table-selection --strict`。
- [x] 3.4 运行相关 focused pytest 后，执行完整 `./.venv/bin/python -m pytest`，所有用例通过后再交付。
