## 1. 测试先行

- [x] 1.1 增加 executor 单测，证明 `editable_table.fill_row target.table=指标挂接规则` 可解析到子表 `fieldid=table_rule`。
- [x] 1.2 增加 executor 单测，证明 `target.table=table_rule_table` 可通过 runtime fieldid 解析到同一子表。
- [x] 1.3 增加 executor 单测，证明表名不匹配错误会列出 label、region fieldid 和 runtime fieldid，而不是只列多个 `表格`。

## 2. 实现

- [x] 2.1 扩展可编辑表格 scope 解析，复用 region 的 `fieldid`、`runtime_fieldids` 和唯一父级语义标题。
- [x] 2.2 改善可编辑表格名称不匹配诊断，输出可用表格身份。
- [x] 2.3 保持既有 `table: 表格` 和列身份候选传递兼容。

## 3. 验证

- [x] 3.1 运行聚焦测试，确认新增测试红绿通过。
- [x] 3.2 运行 `openspec validate support-editable-table-semantic-scope --strict` 和 `./scripts/check_openspec_language.py --change support-editable-table-semantic-scope`。
- [x] 3.3 使用真实 YAML `/Users/ken/temp/ydf-browser-问题反馈/流程-预算执行-工资发放-统发批次发放正向流程 (1).yaml` 验证最后一步可继续执行。
- [x] 3.4 运行完整 pytest 回归。
