## Why

`open_menu` 当前只有在 `content_card` 运行时包含字段、可交互控件或文本时才判定其进入初始终态。Gogs Issue #13 的两个真实用例中，`tbl_card` 已可见且持续稳定为空，树、其它卡片和空表也已完成，但该空卡片仍使 `open_menu` 等待约 117 秒后超时。

现有 `LCDTable` 空表修复只覆盖物理表格根与兄弟空态，不覆盖稳定的空 `content_card`；需要补充共享工作面终态语义，避免把合法的空布局容器误判为页面未就绪。

## What Changes

- 扩展 `open_menu` 首次展示工作面判定：可见的 `content_card` 在无局部加载、无业务错误且内容快照稳定为空时，视为合法的空内容初始终态。
- 继续使用现有状态转换与 500ms 稳定快照；卡片随后出现内容、加载状态、错误或发生显隐变化时，必须重新等待或失败。
- 保持空表、树、非空卡片和 `main_table` 物理身份的既有绑定及后续动作语义不变；不使用页面根或任意祖先容器作为空态兜底。
- 补充结构化工作面证据和共享 runtime 测试，覆盖空卡片放行、加载遮罩阻塞、内容延迟出现和其它工作面并行判定。
- 使用 Issue #13 关联的两个菜单路径进行只包含 `open_menu` 的真实 DSL 验证，确认问题步骤不再阻塞；完整业务链路可能暴露与本 issue 无关的问题，不纳入本 change 验收范围。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `runtime-action-completion-signals`: 明确稳定、无加载和错误证据的空 `content_card` 可以作为首次展示工作面的空内容终态，并保留变化重置与诊断证据要求。

## Impact

- 主要影响 `ydf_browser/runtime.py` 的首次展示工作面扫描和 `open_menu` 等待逻辑。
- 影响 `open_menu` 步骤中的 `work_surfaces` 结构化证据及相关 runtime/executor 测试。
- 不修改 `/Users/huangzy/Downloads/ams-pvdf` 前端设计器源码，不改变 DSL 语法、菜单解析、表格绑定或业务数据。
