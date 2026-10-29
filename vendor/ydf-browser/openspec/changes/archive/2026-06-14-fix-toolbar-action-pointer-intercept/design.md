## Context

当前 runtime 的动作点击链路大致为：executor 根据模板 action 选择 `fieldid` / label，`PlaywrightRuntime._resolve_visible_toolbar_action()` 找到可见候选，最后 `click()` 调 Playwright `locator.click()`。源码真实执行 `/Users/ken/temp/ydf-browser-问题反馈/特性-项目管理-项目预算-YDF-80492-YDFJF-1950-0001 (1).yaml` 时，前 7 步均成功，第 8 步 `toolbar.click 保存` 绑定到 `fieldid=bc_btn`，但 Playwright 点击元素中心点时被右侧 `workbenchRightSidebar-fixedBox` 拦截。

项目里已有同类经验：同一个工具栏 `fieldid` 可能渲染多个可见实例，某个实例会被固定底栏覆盖，运行时应跳过不能接收 pointer event 的候选。当前代码已有 `_receives_pointer_events()`，但它只检查中心点并且只在候选筛选阶段使用；真实点击前滚动、页面布局变化或右侧固定栏遮挡仍会导致 Playwright 点击失败。

## Goals / Non-Goals

**Goals:**

- 让 `toolbar.click 保存` 这类动作在按钮可见但中心点被固定栏、底栏或浮层遮挡时，仍能使用按钮内部可接收 pointer event 的安全点完成点击。
- 让候选筛选和最终点击复用同一套可点击点探测，避免“筛选通过、实际点击失败”的不一致。
- 保持 DSL 语义稳定，不要求用例作者写 DOM selector、坐标、`force` 或其他低层交互。
- 通过单元测试覆盖中心点遮挡但侧边可点、同 `fieldid` 多候选、完全遮挡失败诊断；通过真实源码 CLI 验证该项目授权用例至少越过 `保存` 步骤。

**Non-Goals:**

- 不改变 `toolbar.click`、`action.click`、`table_row_action.click` 的 DSL 结构。
- 不引入全局 `force=True` 点击策略；运行时仍应模拟真实用户可达点击。
- 不针对 `bc_btn`、`workbenchRightSidebar-fixedBox` 或某个菜单写硬编码特殊分支。
- 不保证业务保存后的第 9 步 `可授权金额=400.00` 一定通过；本变更只修复第 8 步动作点击被遮挡的问题。

## Decisions

1. 增加“可点击点”探测 helper，而不是扩大 selector 或直接 `force=True`。

   推荐在 `PlaywrightRuntime` 中增加内部 helper，例如 `_action_click_position(locator)` / `_locator_click_position(locator)`。该 helper 在元素可见后采样多个元素内部点：中心、左中、右中、上中、下中，以及必要时按按钮尺寸裁剪到安全边距。每个点通过 `document.elementFromPoint(x, y)` 验证命中元素本身或其子节点，命中后返回 Playwright 相对坐标。

   替代方案 A 是对 `.workbenchRightSidebar-fixedBox` 设置 `pointer-events: none`，风险是修改页面行为且只覆盖一个遮挡源。替代方案 B 是对所有动作 `force=True`，会绕过真实交互约束，可能把不可点击或被弹窗遮挡的动作误报成功。两者都不适合作为通用 runtime 修复。

2. 让 `_receives_pointer_events()` 复用可点击点探测结果。

   现有 `_receives_pointer_events()` 只检查中心点。实现后它应返回“至少一个安全点击点可接收 pointer event”。这样同 `fieldid` 多实例筛选仍能跳过完全被遮挡的候选，但不会因为中心点被挡而丢弃一个局部可点击的真实按钮。

3. 在通用 `click()` 中优先使用安全点击坐标。

   `click()` 解析 locator 后先探测安全坐标；若存在坐标，调用 `locator.click(position=position)`，再等待稳定。若不存在安全坐标，可继续走原 `locator.click()` 以保留 Playwright 诊断，或在 Playwright 失败后补充页面遮挡诊断。实现阶段应避免吞掉 Playwright 原始错误，因为它包含具体拦截元素。

4. 保持动作候选选择顺序和标签匹配规则。

   对 `fieldid + label` 的严格匹配仍优先。新增可点击点只影响候选是否可点击和最终点击坐标，不改变 `保存`、`授权`、页签同 fieldid 冲突等既有动作身份判断。

## Risks / Trade-offs

- [Risk] 多点探测增加少量浏览器 evaluate 成本。-> Mitigation: 只对动作点击候选执行，候选数量通常很少，且相对 30s click timeout 成本可忽略。
- [Risk] 某些按钮内部图标或文字子节点接收 pointer event，但点击目标仍应是按钮。-> Mitigation: `elementFromPoint` 命中目标子节点时接受，实际 Playwright 仍对按钮 locator 按相对坐标点击。
- [Risk] 完全遮挡的按钮如果 fallback 到原 `locator.click()`，仍会等待到 timeout。-> Mitigation: 可在无安全点时直接抛出包含遮挡元素的诊断；若实现阶段保留原 click，应至少对真实回归控制总耗时。
- [Risk] 横向/纵向滚动后遮挡关系变化。-> Mitigation: 点击前先滚动到稳定位置，再探测点击点；不要用滚动前的坐标缓存。
- [Risk] 部分页面按钮可见区域过窄。-> Mitigation: 采样点应根据元素宽高动态裁剪，避免点落在元素边界外。

## Migration Plan

- 这是 runtime 内部稳定性修复，无 DSL 迁移。
- 现有测试继续保持；新增测试覆盖中心点遮挡、完全遮挡、多候选选择。
- 真实验证使用源码入口 `./.venv/bin/python -m ydf_browser.cli run ...`，不能使用系统安装的 release 二进制。
