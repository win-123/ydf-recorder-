## Why

YonDiF 单据页使用 `YDFStepNext`（WUI Steps）组件承载页签（stepBar 区域），该组件在页面过渡期间（保存后从编辑视图切回列表视图、或 `open_menu` 后页面初始加载）存在异步渲染窗口。当前 `tab.click` 的定位入口 `_resolve_visible_tab_action` 是单次尝试、无重试：一旦命中渲染窗口期，`[fieldid="<tab_fieldid>"]` 选择器无法匹配尚未挂载或不可见的元素，所有兜底选择器也无法匹配 `wui-steps-item-wrap` 类名，导致步骤以"未找到可点击页签"失败。该问题在无头模式下尤为突出，表现为间歇性失败（历史运行中约 37% 失败率），阻断采购计划新增审核正向链路等业务用例。

## What Changes

- 在 `_resolve_visible_tab_action` 中增加短间隔轮询重试机制：当首次选择器匹配失败时，以固定间隔重试直到元素变为可见且可点击，或达到超时上限。
- 重试期间优先使用 manifest 提供的 `fieldid` 定位（`[fieldid="<fieldid>"]`），确保在页面过渡后仍能精确匹配目标页签。
- 在重试耗尽后生成增强诊断信息：包含目标 fieldid 的匹配计数、元素可见性和 bounding box、stepBar 容器的存在性和子元素数量，便于后续排查。
- 不改变 tab.click 的成功语义、完成信号等待逻辑和 DOM 过渡恢复逻辑。

## Capabilities

### New Capabilities

- `tab-action-clicking`: 定义 `tab.click` 动作在页面渲染过渡期间通过轮询重试稳定命中目标页签的能力，包括 fieldid 优先定位、渲染等待超时、可点击性校验和失败诊断要求。

### Modified Capabilities

（无——现有 `toolbar-action-clicking` 和 `runtime-action-completion-signals` 的规格行为不受影响。）

## Impact

- **代码**：`ydf_browser/runtime.py` 中 `_resolve_visible_tab_action` 方法及其调用的 `_find_first_visible_selector` / `_find_first_visible_exact_text_selector`（增加可选的 `retry` 参数）。
- **测试**：`tests/test_runtime.py` 中新增 tab.click 渲染等待和重试场景的单元测试。
- **DSL 语义**：不变——`tab.click` 的输入输出格式、完成信号和错误消息格式保持兼容。
- **性能**：正常路径（元素已渲染）无额外等待；异常路径最多增加约 5 秒重试窗口。
