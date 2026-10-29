## 1. DSL 与文档

- [x] 1.1 在 `ydf_browser/dsl.py` 的结构化弹出参照目标 schema 中允许 `tab`、`tabs`，覆盖 `form.fill`、`editable_table.fill_row` 和 `popup_reference.select` 字段值校验。
- [x] 1.2 增加页签目标校验：支持字符串简写和对象写法中的 `label`、`value`、`name`，拒绝 `selector`、`css`、`xpath`、`locator` 等裸选择器。
- [x] 1.3 更新 `skills/gov-ydfdev-browser/references/dsl-reference.md`，说明 `tab` 是弹出参照内部页签上下文，并补充 `收款方户名` 示例。
- [x] 1.4 增加或更新示例 YAML，覆盖 `收款方户名` 使用 `tab: 本单位人员账户`、`filter: 苏康涯`、`match.column: 户名` 的写法。

## 2. 运行时页签上下文

- [x] 2.1 在 `ydf_browser/runtime.py` 中扩展结构化参照目标归一化和选择目标拆分，保留 `tab` / `tabs` 到每个 selection target。
- [x] 2.2 实现 `_apply_popup_reference_tab_context(...)` 或等价 helper，在当前参照 shell / choice root / iframe context 内精确点击目标页签。
- [x] 2.3 将页签上下文应用顺序接入 `_select_popup_reference(...)` 和 `select_popup_reference(...)`：先 `tab`，再 `tree`，再 `filter` 和候选匹配。
- [x] 2.4 页签点击后重新解析 choice root 并等待候选区稳定，避免继续使用切换前的旧表格或旧过滤框。
- [x] 2.5 页签缺失时抛出明确错误，包含目标页签和当前参照可见页签候选或诊断文本。

## 3. 过滤与诊断

- [x] 3.1 确认标量 `filter` 走通用搜索框路径，适配 `输入关键字搜索` 这类无业务标签输入框。
- [x] 3.2 保持 `filter.conditions` 的带标签查询字段语义；当只有通用搜索框时，错误信息应提示改用标量 `filter`。
- [x] 3.3 将 `popup_tab_context` 写入 `last_popup_reference_result`，并保持 `selected`、`confirmed`、`confirm_label`、`popup_tree_context` 兼容。
- [x] 3.4 在 `editable_table.fill_row` 字段级结果中透传参照诊断，至少包括 `popup_tab_context` 以及运行时返回的既有参照诊断字段。

## 4. 回归测试

- [x] 4.1 增加 DSL 单测，覆盖接受 `tab` / `tabs`、拒绝裸选择器、缺少最终选择目标时失败。
- [x] 4.2 增加 runtime 单测，覆盖参照根内页签切换、已激活页签幂等、背景同名页签不被点击、页签缺失错误诊断。
- [x] 4.3 增加 executor/runtime 测试，覆盖 `editable_table.fill_row` 中 `YDFReferSelect` 单元格使用 `tab + filter + match` 并报告 `popup_tab_context`。
- [x] 4.4 增加兼容测试，确认不带 `tab` 的既有 `tree`、`filter`、`match`、`first_available` 参照行为不回归。

## 5. 真实验证

- [x] 5.1 使用源码入口校验目标 YAML 或整理后的临时 YAML：`./.venv/bin/python -m ydf_browser.cli validate --dsl <yaml>`。
- [x] 5.2 真实执行 `/Users/ken/temp/ydf-browser-问题反馈/ar01_报销管理_借款单填报 (1).yaml` 或整理后的等价用例，确认能越过 `editable_table.fill_row` 的 `收款方户名` 录入。
- [x] 5.3 检查真实报告，确认 `收款方户名` 字段结果包含 `popup_tab_context=本单位人员账户`，且目标单元格已回填 `苏康涯` 或等价参照带出信息。
- [x] 5.4 运行聚焦测试和 OpenSpec 校验：`./.venv/bin/python -m pytest tests/test_dsl.py tests/test_runtime.py tests/test_executor.py -q`、`openspec validate support-popup-reference-tabs --strict`。
