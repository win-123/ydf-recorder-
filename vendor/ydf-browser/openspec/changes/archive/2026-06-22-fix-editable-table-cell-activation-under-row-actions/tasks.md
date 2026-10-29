## 1. 回归复现

- [x] 1.1 在 `tests/test_runtime.py` 增加最小回归，构造可编辑表格单元格上方存在 `插入`、`复制`、`删除` 或更多行级动作浮层的 DOM，验证激活逻辑避开动作按钮。
- [x] 1.2 确认现有 `editable_table.fill_row` 单元格身份定位测试仍覆盖 `fieldid/dataField/tableFieldid` 传递和每列重新定位。

## 2. Runtime 实现

- [x] 2.1 调整 `ydf_browser/runtime.py` 的可编辑表格单元格激活点击点选择，识别并跳过行级动作按钮、更多按钮和 action-like 覆盖层。
- [x] 2.2 在编辑器未出现且疑似被行级浮层遮挡时，做一次短重试：重新解析目标单元格并选择未被覆盖的可点击区域。
- [x] 2.3 保持失败路径输出表格、行号、列名、目标列身份或定位来源，以及截图路径。

## 3. 验证

- [x] 3.1 运行相关单测：`./.venv/bin/python -m pytest tests/test_runtime.py -k "editable_table_cell or editable_table"`
- [x] 3.2 真实执行问题 YAML：`./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/功能-预算管理-项目库（高校）-收入项目管理-储备项目-复制新增-0001.yaml --headless --report-file /tmp/ydf-income-reserve-copy-add-after-fix.json`
- [x] 3.3 检查真实报告，确认执行越过 `测算依据及说明` 录入；如果后续保存失败，区分为独立业务校验而不是本 change 的单元格激活失败。
- [x] 3.4 运行 OpenSpec 门禁：`openspec validate fix-editable-table-cell-activation-under-row-actions --strict` 和 `./scripts/check_openspec_language.py --change fix-editable-table-cell-activation-under-row-actions`。
