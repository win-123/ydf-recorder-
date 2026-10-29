## 1. 回归测试先行

- [x] 1.1 新增 `_popup_reference_dialog_hidden_now` 回归：dialog 外壳只含可见 iframe、实际候选表格与 `确定/取消` 位于子 frame、子 frame URL 与标题不含参照关键字时，判定为仍未关闭；验证 `./.venv/bin/python -m pytest tests/test_runtime.py -q -k "popup_reference_hidden_now"` 通过
- [x] 1.2 新增 `_popup_reference_root_value_backfilled` 回归：plain `first_available` 且根读取结果为“请选择”时不得视为已回填；验证对应聚焦 pytest 通过
- [x] 1.3 新增可编辑表格整链回归：候选已勾选、单元格仍为“请选择”、dialog 外壳含 iframe 时不得以 `close_action=target-backfill` 提前返回，必须继续点击确认并等待回填；验证聚焦 pytest 通过
- [x] 1.4 保持既有自动关闭且目标单元格真实回填的成功路径测试通过，验证对应 `target-backfill` 聚焦 pytest 通过

## 2. 共享运行时修复

- [x] 2.1 调整 `_popup_reference_dialog_hidden_now`：dialog 根内无候选面时，先探测 dialog 是否包含可见 iframe，并只扫描这些 iframe 对应的子 frame 文档；发现可见候选面与 `确定/确认/保存`、`取消` 时返回未关闭
- [x] 2.2 复用现有 dialog→frame 归属判断（与 `_resolve_current_popup_reference_choice_root`、`_click_popup_reference_confirm` 同源），不新增页面或字段专用分支
- [x] 2.3 按设计决定调整或保留 `_has_visible_popup_reference_surface_in_search_contexts` 兜底门槛：结构证据优先，关键字仅用于降低误报；不得先要求 URL/标题命中再检查结构
- [x] 2.4 调整 `_popup_reference_root_value_backfilled`：将“请选择”“暂无数据”等空态占位文本归一化为空值，阻止 plain `first_available` 假回填
- [x] 2.5 保持 `close_action`、`confirmed`、`confirm_label`、候选选中态和失败截图诊断字段稳定，验证相邻 popup reference 聚焦测试通过

## 3. 测试回归

- [x] 3.1 运行 popup reference 与 editable table 相邻聚焦测试，确认共享 runtime 改动未破坏普通表单参照、iframe 保存确认、背景保存隔离和自动关闭回填路径
- [x] 3.2 运行完整 `./.venv/bin/python -m pytest`，确认全量测试通过

## 4. 真实 DSL 验收

- [x] 4.1 使用当前源码执行 `流程-单位资金分散-批量支付-正向流程（审核）-001` 的 `batch_payment_apply_decentral`，验证第 7 步 `editable_table.fill_row` 能选择第一行、点击“确定”、关闭弹窗并回填“收款人全称”
- [x] 4.2 使用当前源码执行 `流程-预算执行-预算拨款-外贷拨款申请流程-外贷提款-0001` 的同类用例，验证嵌套 iframe 参照确认链路通过
- [x] 4.3 检查真实报告中的候选选中态、`confirmed`、`confirm_label`、`close_action`、frame 和字段回填证据；后续独立业务数据失败不得扩大本 change 范围

## 5. 文档与门禁

- [x] 5.1 运行 `openspec validate fix-nested-iframe-popup-reference-hidden-detection --strict` 通过
- [x] 5.2 运行 `./scripts/check_openspec_language.py --change fix-nested-iframe-popup-reference-hidden-detection` 通过
- [x] 5.3 运行 `git diff --check` 通过
