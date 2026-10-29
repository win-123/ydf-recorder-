## 1. 回归测试

- [x] 1.1 在 `tests/test_runtime.py` 增加字段弹出参照标量值的测试：首次输入后候选仍有歧义，提交搜索过滤并重新解析后收敛为唯一候选。
- [x] 1.2 增加自动过滤快路径测试，确认首次输入已经得到唯一候选时不执行重复提交。
- [x] 1.3 增加提交后仍有多个候选的测试，确认只重试一次、保留候选数量和选择建议，并且不默认选择第一条。
- [x] 1.4 覆盖独立 `popup_reference.select` 和 `editable_table.fill_row` 复用该语义的相邻入口，确认结构化 `match`、`first_available` 和显式 `filter` 行为不回退。

## 2. 运行时实现

- [x] 2.1 在现有弹出参照候选选择边界识别“标量唯一性歧义 + 隐式过滤尚未提交”的可恢复情况，调用既有搜索图标/回车提交逻辑并限制最多一次重试。
- [x] 2.2 过滤提交后重新解析当前前景候选根，再执行唯一候选匹配、选择态确认和字段回填；其它候选解析或确认异常继续直接失败。
- [x] 2.3 保留提交重试后的原有歧义诊断，并确认 `form.fill`、`editable_table.fill_row`、`popup_reference.select` 的共享调用者没有页面专用分支或默认首选行为。

## 3. 验证与真实用例

- [x] 3.1 运行 `./.venv/bin/python -m pytest tests/test_runtime.py -q` 及本 change 新增的聚焦测试。
- [x] 3.2 使用当前源码运行 `/Users/ken/temp/ydf-browser-问题反馈/fund_counterpart_basic_maintenance.yaml`，确认银行网点字段完成过滤、唯一选择和目标单元格回填；若后续保存或业务校验失败，单独记录其原因。
- [x] 3.3 运行完整 `./.venv/bin/python -m pytest -q`、`openspec validate fix-popup-reference-implicit-filter-submit --strict`、`./scripts/check_openspec_language.py --change fix-popup-reference-implicit-filter-submit` 和 `git diff --check`。
