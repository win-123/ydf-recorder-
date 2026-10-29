## 1. 复现与测试先行

- [x] 1.1 增加 runtime 单测，复现弹出参照表格行点击后只有行根 `.selected`、行内 `input.checked=false` 时当前选择态判断失败的问题。
- [x] 1.2 增加 row-number 选择单测，覆盖 `_click_popup_reference_table_row_by_index()` 点击 WUI radio 后应接受行级 selected。
- [x] 1.3 增加主子表顺序选择单测，覆盖 `selections` 先选 `项目预算` 主表行，再等待/解析 `预算编制科目` 子表行。

## 2. Runtime 修复

- [x] 2.1 调整 `ydf_browser/runtime.py` 中弹出参照候选选中态 helper，让表格行根 `selected` / `aria-selected=true` 成为有效选中证据。
- [x] 2.2 确保选中态判断限定在当前弹出参照和当前表格行根内，避免背景页表格、分页行、合计行或固定列副本造成误判。
- [x] 2.3 调整 row-number / first_available / match 相关路径，复用统一的弹出参照候选选中态判断。
- [x] 2.4 对主子表 `selections` 在每次选择后刷新 choice root / table root，并等待下一张表出现可选择数据。

## 3. 诊断与报告

- [x] 3.1 保持失败诊断可读：若行存在但未形成任何有效选中态，错误信息和截图仍能定位到当前弹窗表格内容。
- [x] 3.2 确认成功步骤结果保留 `selected` 列表，包含 `项目预算` 和 `预算编制科目` 两个 selection。

## 4. 验证

- [x] 4.1 运行相关单测，例如 `./.venv/bin/python -m pytest tests/test_runtime.py -k "popup_reference"`，并根据变更范围补跑 executor/dsl 相关测试。
- [x] 4.2 运行 `./.venv/bin/python -m ydf_browser.cli validate --dsl /Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-项目预算-YDF-81116-0001.yaml`。
- [x] 4.3 真实执行 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-项目预算-YDF-81116-0001.yaml`，确认第 6 步能选中 `项目预算` 主表和 `预算编制科目` 子表，并关闭弹窗。
- [x] 4.4 运行 `openspec validate fix-popup-reference-row-selection-state --strict`。
