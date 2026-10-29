## 1. 回归测试

- [x] 1.1 在 `tests/test_runtime.py` 增加 `first_available` 候选采集回归：空状态候选和真实商品业务行同时存在时，必须选择真实业务行。
- [x] 1.2 在 `tests/test_runtime.py` 增加带 radio/checkbox 的商品表格行选中态回归，确认点击后必须验证 checked、selected 或 aria checked/selected。
- [x] 1.3 补充失败诊断回归，覆盖业务行可见但未选中时错误信息包含候选数量、候选来源、候选文本摘要和截图路径。

## 2. 运行时修复

- [x] 2.1 调整 `_click_first_popup_reference_candidate()` 的候选采集，过滤 `暂无数据`、`暂时没有数据`、查询空态、表头、分页、footer 和非业务文本节点。
- [x] 2.2 保持有效右侧候选表格优先，但只把可见业务数据行作为 `candidate_source=right-table` 的可尝试候选。
- [x] 2.3 对带 radio/checkbox 的业务行优先点击选择控件或其包装节点，并复用现有选中态校验。
- [x] 2.4 保留普通树、列表和无选择控件候选的既有兼容行为，避免把右表过滤失败扩散成其它参照失败。
- [x] 2.5 改进 `first_available` 失败诊断，区分有效候选、被排除空状态和实际尝试候选。

## 3. 真实验证

- [x] 3.1 运行聚焦单测：`./.venv/bin/python -m pytest tests/test_runtime.py -k "first_available and popup_reference"`。
- [x] 3.2 真实运行 `/Users/ken/temp/ydf-browser-问题反馈/功能-单位收入管理-来款认领-项目认领-补开发票-002.yaml`，确认第 8 步 `发票内容明细.商品` 能选中商品业务行。
- [x] 3.3 如果真实用例越过第 8 步后失败，按报告区分后续独立业务问题，不能把后续失败算作本修复未完成。
- [x] 3.4 运行完整测试：`./.venv/bin/python -m pytest`。

## 4. OpenSpec 门禁

- [x] 4.1 运行 `openspec validate fix-popup-first-available-visible-table-row --strict`。
- [x] 4.2 运行 `./scripts/check_openspec_language.py --change fix-popup-first-available-visible-table-row`。
