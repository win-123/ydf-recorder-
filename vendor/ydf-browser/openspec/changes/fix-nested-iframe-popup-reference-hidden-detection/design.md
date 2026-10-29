## Context

真实 DSL 复现（run `20260826-151034-19b606fa`）显示：`editable_table.fill_row` 第 7 步已勾选第一行候选，但运行时在单元格仍显示“请选择”时打印 `stage=root-backfill value=True`，随后以 `close_action=target-backfill` 提前返回，未点击“确定”；失败瞬间 `tablePayeeAccount` 候选表格与“确定/取消”仍位于 `yondif-pvdf-fe/ucf-wh/index.html` 子 frame 中。

当前共享关闭判定 `_popup_reference_dialog_hidden_now` 只检查传入 dialog 根内部是否有候选面；候选面位于 dialog 所包含 iframe 时，根内检查必然失败，只能依赖 `_has_visible_popup_reference_surface_in_search_contexts`。该扫描以 URL 关键字（`PM_SELECT_MANAGER`、`select`、`reference`、`refer` 等）或标题关键字（`参照`、`选择`、`人员` 等）作为前置门槛，而本次子 frame URL 为 `yondif-pvdf-fe/ucf-wh/index.html`、页面标题为“收款人账户备案”，均不命中，因此返回“无可见参照面”，触发误判。

代码中已有两条可复用的桥接能力：`_resolve_current_popup_reference_choice_root` 会探测 dialog 是否含可见 iframe 并把候选根解析到子 frame；`_click_popup_reference_confirm` 通过 `dialog.contains(frame.frame_element())` 在 dialog 所属 frame 内点击确认按钮。关闭判定没有复用同一归属关系。

## Goals / Non-Goals

**Goals:**

- 让“dialog 外壳含 iframe、实际候选面在子 frame”的形态被共享关闭判定识别为仍未关闭。
- 让 `first_available` 空态占位文本（“请选择”）不参与 `target-backfill` 早退。
- 复用现有 dialog→frame 归属判断，不新增页面或字段专用分支。
- 保持自动关闭且目标单元格真实回填的既有成功路径。

**Non-Goals:**

- 不改变 DSL schema、候选选择语义或确认按钮标签语义。
- 不重构完整弹出参照定位体系。
- 不为 `收款人全称`、`PAYEE_ACCOUNT_MANAGE_SELECT` 或 `收款人账户备案` 增加特例。

## Decisions

### 1. 关闭判定优先按 dialog 包含的 frame 搜索候选面

当 dialog 根可见但根内 `dialog.evaluate` 找不到候选面时，先探测 dialog 是否包含可见 iframe；若包含，则只扫描这些 iframe 对应的子 frame 文档，判定条件与现有扫描一致：同一 frame 内存在可见候选表格/树、`确定/确认/保存` 和 `取消`。

备选方案：直接放宽 `_has_visible_popup_reference_surface_in_search_contexts` 的 URL/标题门槛。该方案会让主页面背景表格和保存按钮更容易被当成参照面，违背“背景保存按钮不表示参照仍可见”的既有行为，因此不采用。

### 2. 跨 frame 全局扫描保留为兜底

dialog locator 因 frame 重渲染不可读或失效时，继续使用 `_has_visible_popup_reference_surface_in_search_contexts` 作为兜底；其 URL/标题门槛可以保守收紧为“结构证据优先、关键字仅用于降低误报”，但不得先要求命中关键字再检查结构。若实现时发现该改动会提升背景误报，则保持现有门槛不变，把 dialog 包含 frame 的路径作为唯一修复入口。

### 3. 根回填判定识别空态占位文本

在 `_popup_reference_root_value_backfilled` 进入 plain first_available 早退分支前，把“请选择”“暂无数据”“暂无数据哦”等空态占位文本归一化为空值。复用现有 `_popup_reference_candidate_text_is_empty_state` 一类的空态识别思路，避免为根值单独发明一套新标记。

备选方案：在 `_FIELD_VALUE_FROM_ROOT_SCRIPT` 中不再返回直接文本。该改动影响普通表单字段的值读取，回归面过大，不采用。

## Risks / Trade-offs

- [Risk] dialog 包含 frame 的扫描可能因 frame 元素与 dialog 根不在同一文档而漏检 → Mitigation: 保留全局扫描兜底，并在聚焦测试中覆盖“shell 含 iframe”和“旧 locator 失效”两种形态。
- [Risk] 空态占位文本归一化影响“请选择”确实作为业务值的罕见字段 → Mitigation: 只精确匹配已知空态标记，且只影响弹出参照根回填判定，不改变表单填值语义。
- [Risk] 自动关闭且已回填的成功路径被误伤 → Mitigation: 保持 `target-backfill` 需要“候选层真实关闭 + 目标单元格真实回填”的共同条件，回归测试同时锁定该路径。

## Migration Plan

本变更为仓库内运行时修复，无数据迁移。发布按现有 wheel 与 runtime 更新流程执行；回滚为还原提交并重新发布。

## Open Questions

- 全局兜底扫描的 URL/标题门槛是否收紧，可在实现阶段根据聚焦测试和真实 DSL 验证结果决定，不影响规格与任务拆分。
