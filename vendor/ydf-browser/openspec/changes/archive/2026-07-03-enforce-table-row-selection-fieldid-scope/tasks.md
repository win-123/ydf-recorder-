## 1. 回归测试

- [x] 1.1 增加 runtime 单测，复现 `table_fieldid` 根存在但无可选行时，旧逻辑会按 `target.table` 文本回退到其它表格并误选。
- [x] 1.2 增加 executor 或 runtime 单测，覆盖选行成功后报告包含实际表格根 `fieldid/source/selectableRows`。
- [x] 1.3 保留或补充 WUI header/body 分离聚合用例，确认同一 `table_fieldid` 下的分离表头表体仍可选择。

## 2. 实现

- [x] 2.1 调整 `ydf_browser/runtime.py` 的 `_table_selection_context()`，当已传入 `table_fieldid` 时不再按 `target.table` 文本回退到其它表格根。
- [x] 2.2 在 fieldid 根无可选业务行或无法点击时，保留目标 `table`、`table_fieldid` 和已命中根摘要到失败诊断。
- [x] 2.3 将 runtime 实际命中的表格根摘要附加到成功步骤的 `selection_debug` 或等价诊断对象。

## 3. 验证

- [x] 3.1 运行新增 focused pytest，确认旧的跨表格回退误选失败、同 fieldid header/body 聚合仍通过、成功报告含实际根摘要。
- [x] 3.2 运行 `openspec validate enforce-table-row-selection-fieldid-scope --strict` 和 `./scripts/check_openspec_language.py --change enforce-table-row-selection-fieldid-scope`。
- [x] 3.3 运行全量 `./.venv/bin/python -m pytest`。
- [x] 3.4 使用修正后的真实 DSL `/Users/ken/temp/ydf-browser-问题反馈/功能-单位收入管理-来款认领-项目认领-补开发票-002.yaml` 回归第一用例，确认 `table: 表格` 仍解析到 `second_table` 并提交成功。
