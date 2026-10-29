## 1. 回归测试

- [x] 1.1 在 `tests/test_runtime.py` 增加 `first_available` 轻量候选左侧 checkbox 未勾选时不能算成功的回归测试。
- [x] 1.2 覆盖候选无 checkbox/radio 时仍保持既有成功路径。

## 2. 运行时修复

- [x] 2.1 调整 `ydf_browser/runtime.py` 中 `_click_first_popup_reference_candidate()` 的候选识别，让候选 DOM 或同一候选行内存在可见 checkbox/radio 时标记为 `requiresSelection=true`。
- [x] 2.2 复用 `_stabilize_popup_reference_selection()` 和 `_popup_reference_candidate_has_selection_state()`，确保未读到 checked/selected 状态时继续尝试下一个候选或失败。
- [x] 2.3 保持弹出参照根范围限定在当前 choice root，避免背景页或外层业务弹窗参与候选选择。

## 3. 验证

- [x] 3.1 运行新增/相关单测：`./.venv/bin/python -m pytest tests/test_runtime.py -k "first_available and popup_reference"`。
- [x] 3.2 运行真实问题用例：`./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/实物管理-易耗品物资-盘点任务下发-未下发页签新增-0001.yaml --headless --report-file /tmp/ydf-inventory-issue-location-after.json`，确认 `存放地点` 不再因 `请选择数据！` 失败。
- [x] 3.3 运行完整测试：`./.venv/bin/python -m pytest`。
- [x] 3.4 运行 OpenSpec 门禁：`openspec validate fix-popup-reference-first-available-checkbox --strict` 和 `./scripts/check_openspec_language.py --change fix-popup-reference-first-available-checkbox`。
