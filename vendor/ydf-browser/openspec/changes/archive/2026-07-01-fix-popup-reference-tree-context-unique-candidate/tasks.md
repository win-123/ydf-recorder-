## 1. 回归测试

- [x] 1.1 在 `tests/test_runtime.py` 增加树形弹出参照标量候选去重测试：路径文本和叶子文本指向同一目标时不报歧义。
- [x] 1.2 确认既有真实多候选歧义测试仍然失败在多候选，不回退为取第一条。
- [x] 1.3 增加候选点击后字段已回填但候选选中态未验证成功时不得继续重试的回归测试。
- [x] 1.4 增加候选 DOM 关闭或失效时选中态读取必须使用短超时的回归测试。
- [x] 1.5 增加候选弹层隐藏判断和跨 frame 候选面扫描必须使用短超时的回归测试。
- [x] 1.6 增加标量唯一候选路径失败后不得继续旧式列表/树/表格兜底查找的回归测试。

## 2. 运行时修复

- [x] 2.1 在标量弹出参照唯一候选路径中传递目标标量值，供候选去重使用。
- [x] 2.2 调整树候选唯一性去重：存在精确叶子候选时，将祖先路径包装候选合并到该叶子候选。
- [x] 2.3 保持 checkbox/radio 真实选中态验证和显式 `first_available`、`row_number`、列表、`selections` 语义不变。
- [x] 2.4 在候选点击返回未选中前，若字段已回填且候选弹层已隐藏，则直接返回成功，避免继续提交过滤或二次查找候选。
- [x] 2.5 为候选选中态读取和稳定化重试增加短超时，避免弹层关闭后的失效 locator 触发浏览器默认长等待。
- [x] 2.6 为候选弹层隐藏判断和跨 frame 参照面扫描增加短超时，避免成功回填后的状态判断继续长等待。
- [x] 2.7 标量唯一候选路径返回未选中时直接交回外层回填检查，不再继续旧式列表/树/表格兜底查找。

## 3. 验证

- [x] 3.1 运行聚焦测试：`./.venv/bin/python -m pytest tests/test_runtime.py -k "popup_reference_scalar_unique"`.
- [x] 3.2 运行真实 YAML：`./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/流程-预算执行-工资发放-统发批次发放正向流程.yaml --headless --report-file /tmp/ydf-salary-batch-flow-report-fixed.json`.
- [x] 3.3 运行 OpenSpec 门禁：`openspec validate fix-popup-reference-tree-context-unique-candidate --strict` 和 `./scripts/check_openspec_language.py --change fix-popup-reference-tree-context-unique-candidate`.
- [x] 3.4 运行完整测试：`./.venv/bin/python -m pytest`.
- [x] 3.5 运行聚焦性能回归测试：`./.venv/bin/python -m pytest tests/test_runtime.py -k "popup_reference and (candidate_state_checks_use_short_timeout or stabilize_retries_use_short_timeout or scalar_unique or table_match_requires_checked_control or backfill_after_unverified_candidate_click)"`.
- [x] 3.6 运行聚焦隐藏判断性能回归测试：`./.venv/bin/python -m pytest tests/test_runtime.py -k "popup_reference and (hidden_now or candidate_state_checks_use_short_timeout or stabilize_retries_use_short_timeout or scalar_unique or table_match_requires_checked_control or backfill_after_unverified_candidate_click)"`.
- [x] 3.7 运行聚焦兜底回归测试：`./.venv/bin/python -m pytest tests/test_runtime.py -k "popup_reference and (scalar_target_does_not_fallback_after_unique_candidate_failure or scalar_unique_table_candidate_failure_defers_screenshot or hidden_now or candidate_state_checks_use_short_timeout or stabilize_retries_use_short_timeout or scalar_unique or backfill_after_unverified_candidate_click)"`.
