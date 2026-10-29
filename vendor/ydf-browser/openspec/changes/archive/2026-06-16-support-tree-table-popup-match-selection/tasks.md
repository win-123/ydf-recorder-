## 1. 复现与测试保护

- [x] 1.1 保留原始失败报告证据，确认 `/Users/ken/temp/ydf-browser-问题反馈/实物管理-易耗品物资-入库填报-新增-0001 2.yaml` 当前失败在 `物资分类 tree + match(物资编码)`。
- [x] 1.2 增加运行时单测，覆盖树表弹出参照在应用 `tree` 后，`match.column` 能识别 W table 右侧候选表头和目标行。
- [x] 1.3 增加运行时单测，覆盖 `match.column` 路径找不到候选时输出目标列、目标值、表头、候选行和截图诊断。
- [x] 1.4 保留或补充兼容性单测，确认 `tree + first_available` 仍优先选择右侧第一条候选并确认回填。

## 2. 核心实现

- [x] 2.1 对齐 `match.column` 与 `first_available` 的候选表格识别口径，覆盖 `.w-table`、`.w-table-row`、`.w-table-cell` 和分离表头/表体形态。
- [x] 2.2 调整树上下文应用后的候选根解析：选择左树后重新解析当前活动参照弹窗内的右侧候选区域。
- [x] 2.3 在执行 `match` 前等待右侧候选表格刷新到可匹配状态，避免在左树区域或旧候选根上匹配。
- [x] 2.4 点击匹配行时优先点击行内选择控件；没有选择控件时点击可接收 pointer event 的行或首个有效单元格。

## 3. 诊断与错误收口

- [x] 3.1 扩展 `match` 失败诊断，包含目标列、目标值、可见表头、候选行摘要、选择控件摘要和截图路径。
- [x] 3.2 当截图可见目标数据但结构化诊断为空时，错误仍在当前字段失败，并明确表现为候选表格未识别或候选根不正确。
- [x] 3.3 确保结构化参照失败不会继续录入 `存放仓库` 或 `入库数量`，避免把第一失败点延迟到后续列。

## 4. 真实验证

- [x] 4.1 使用当前源码运行 `examples/material_stockin_material_category_popup_reference.yaml`，确认既有 `tree + first_available` 样例仍通过。
- [x] 4.2 使用当前源码运行 `/Users/ken/temp/ydf-browser-问题反馈/实物管理-易耗品物资-入库填报-新增-0001 2.yaml`，确认不再失败于 `物资分类 tree + match(物资编码)`。
- [x] 4.3 如果原始用例继续失败于 `存放仓库`、保存或业务校验，保留报告并将其作为独立问题归因，不把它并入本变更范围。

## 5. 收尾验证

- [x] 5.1 运行 `openspec validate support-tree-table-popup-match-selection --strict`。
- [x] 5.2 运行相关单测，例如 `./.venv/bin/python -m pytest tests/test_runtime.py -k "popup_reference or editable_table"`。
- [x] 5.3 按仓库约定运行全量 `./.venv/bin/python -m pytest`，确保所有测试通过。
- [x] 5.4 运行 `git diff --check`，确认文档和代码无空白错误。
