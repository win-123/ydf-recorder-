## 1. 回归测试

- [x] 1.1 在 `tests/test_runtime.py` 增加单元回归，复现参照候选已选中但 iframe/非标准前景参照仍可见时 `_popup_reference_dialog_hidden_now()` 不能返回已关闭。
- [x] 1.2 增加 `form.fill` 弹出参照流程回归，验证选中候选后仍可见 `保存/取消` 页脚时会继续点击 `保存`，并记录 `confirmed=true`、`confirm_label=保存`。
- [x] 1.3 确认既有自动关闭、点击候选即回填、普通 `保存/取消` 弹框和普通下拉测试仍覆盖兼容路径。

## 2. Runtime 修复

- [x] 2.1 调整 `ydf_browser/runtime.py` 中弹出参照关闭检测，扫描当前页面及子 frame 的可见参照前景层，避免把 `PM_SELECT_MANAGER` iframe 参照误判为已关闭。
- [x] 2.2 保持确认点击逻辑复用现有 `_click_popup_reference_confirm*` 路径，确保仍可见参照会点击弹框内 `保存`，而不是背景编辑页 `保存`。
- [x] 2.3 保持 `selected`、`confirmed`、`confirm_label` 诊断字段稳定输出，失败时保留诊断截图和当前 frame 信息。

## 3. 验证

- [x] 3.1 运行新增和相关既有单元测试，例如 `./.venv/bin/python -m pytest tests/test_runtime.py -k "popup_reference"`。
- [x] 3.2 运行真实用例 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-项目库-YDF-82797-0001-执行项目新增父子项目和设置经费管理员.yaml`，确认至少越过 `项目负责人` 后的 `tab.click 财务核算信息`，且报告中 `项目负责人` 为 `confirmed=true`、`confirm_label=保存`。
- [x] 3.3 运行 `openspec validate fix-popup-reference-iframe-save-confirm --strict`。
- [x] 3.4 按仓库要求运行全量验证：`./.venv/bin/python -m pytest`。
