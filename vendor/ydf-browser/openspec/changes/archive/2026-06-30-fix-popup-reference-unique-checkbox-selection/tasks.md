## 1. 回归测试

- [x] 1.1 在 `tests/test_runtime.py` 增加标量短值过滤出唯一 checkbox 候选时必须真实勾选并成功回填的失败测试。
- [x] 1.2 增加标量短值过滤出多个业务候选时失败且不选择第一条或全部的测试，并覆盖候选数量与迁移提示诊断。
- [x] 1.3 增加固定列或虚拟布局产生同一业务行 DOM 副本时不误报歧义的测试。
- [x] 1.4 增加 `match.equals`、`match.contains` 命中带选择控件候选时验证 checked 状态，以及无选择控件、`first_available`、`row_number` 和显式多选保持兼容的测试。

## 2. 运行时修复

- [x] 2.1 在 `ydf_browser/runtime.py` 的标量弹出参照隐式过滤路径中统计并去重当前可选择业务候选，只允许唯一候选进入选择流程。
- [x] 2.2 复用现有候选稳定与选中态读取逻辑，使标量值和 `match` 路径在候选含 checkbox/radio 时点击真实控件并要求可验证的 checked 状态。
- [x] 2.3 收紧带选择控件候选的成功判定，避免仅凭行焦点、蓝色高亮、`active` 或宽泛 `selected` 返回成功，同时保持无选择控件和显式行号场景兼容。
- [x] 2.4 在零候选和多候选失败诊断中记录候选数量，并提示使用完整值、`first_available`、`row_number`、列表或 `selections` 明确选择意图。

## 3. 验证

- [x] 3.1 运行新增及相关测试：`./.venv/bin/python -m pytest tests/test_runtime.py -k "popup_reference and (scalar or unique or checkbox or match)"`。
- [x] 3.2 使用 `/Users/ken/temp/ydf-browser-问题反馈/9_1采购计划编制_预算 (1).yaml` 的截断复现用例，将 `预算项目` 写为 `二级采购项目`，确认唯一候选 checkbox 被勾选且 `form.fill` 成功。
- [x] 3.3 运行完整测试：`./.venv/bin/python -m pytest`。
- [x] 3.4 运行 OpenSpec 门禁：`openspec validate fix-popup-reference-unique-checkbox-selection --strict` 和 `./scripts/check_openspec_language.py --change fix-popup-reference-unique-checkbox-selection`。
