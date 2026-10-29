## 1. 回归测试

- [x] 1.1 在 `tests/test_runtime.py` 增加可点击点探测单元测试，覆盖按钮中心点被遮挡但按钮内部其它点可接收 pointer event 的场景。
- [x] 1.2 增加通用 `click()` 单元测试，验证存在安全点击坐标时调用 `locator.click(position=...)`，而不是默认中心点点击。
- [x] 1.3 扩展或新增同 `fieldid` 多候选测试，覆盖第一个实例完全遮挡、后续实例可点击时选择后续实例的行为。
- [x] 1.4 增加完全遮挡场景测试，确认 runtime 不使用 `force=True` 误报成功，并保留明确诊断。
- [x] 1.5 保留并运行既有 `tests/test_runtime.py::test_playwright_runtime_fieldid_action_skips_visible_button_blocked_by_footer`，防止固定底栏遮挡回归。

## 2. Runtime 实现

- [x] 2.1 在 `ydf_browser/runtime.py` 增加内部点击点探测 helper，先滚动到稳定位置，再基于元素实际矩形采样中心、左右、上下等安全点。
- [x] 2.2 让 helper 通过 `document.elementFromPoint` 判断采样点是否命中目标元素或其子节点，并返回 Playwright 可用的元素相对坐标。
- [x] 2.3 修改 `_receives_pointer_events()` 复用点击点探测结果，使候选筛选不再只依赖中心点。
- [x] 2.4 修改通用 `click()`，在存在安全点击坐标时调用 `locator.click(position=...)`，没有安全点时保留或补充遮挡诊断。
- [x] 2.5 确认 `toolbar.click`、`action.click`、`table_row_action.click` 等复用通用点击路径的动作不需要 DSL 变更。

## 3. 聚焦验证

- [x] 3.1 运行聚焦单测：`./.venv/bin/python -m pytest tests/test_runtime.py::test_playwright_runtime_fieldid_action_skips_visible_button_blocked_by_footer` 以及本 change 新增测试。
- [x] 3.2 运行相关 runtime 测试片段，覆盖工具栏动作、`fieldid` 动作、动态下拉按钮和下载动作不受影响。
- [x] 3.3 使用源码入口真实执行 `/Users/ken/temp/ydf-browser-问题反馈/特性-项目管理-项目预算-YDF-80492-YDFJF-1950-0001 (1).yaml`，确认至少越过第 8 步 `toolbar.click 保存`。
- [x] 3.4 如果第 9 步 `可授权金额` 断言失败，记录新的业务或断言失败证据，不把它和本 change 的点击修复混为一谈。

## 4. OpenSpec 验收

- [x] 4.1 运行 `openspec validate fix-toolbar-action-pointer-intercept --strict`。
- [x] 4.2 运行 `openspec status --change "fix-toolbar-action-pointer-intercept"`，确认 tasks 已可用于 apply。
- [x] 4.3 更新交付说明，列出源码验证命令、真实报告路径和是否越过 `保存` 步骤。
