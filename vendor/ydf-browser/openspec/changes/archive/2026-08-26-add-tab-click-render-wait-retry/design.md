## Context

当前 `_resolve_visible_tab_action`（`ydf_browser/runtime.py`）的实现是单次遍历所有选择器：

```python
def _resolve_visible_tab_action(self, action_label: str, fieldid: str | None = None) -> BoundElement:
    selector = self._find_first_visible_selector(build_tab_action_selectors(action_label, fieldid=fieldid))
    if selector is None:
        selector = self._find_first_visible_exact_text_selector(build_tab_exact_text_selectors(), action_label)
    if selector is None:
        raise RuntimeError(f"未找到可点击页签: {action_label}")
    return self._build_visible_action_bound_element(action_label, selector, reason="visible_tab_action")
```

`_find_first_visible_selector` 对每个选择器在每个 frame 中执行一次 `locator.count()` + 逐个检查 `is_visible` 和 `_is_clickable_action_target`。如果元素在 DOM 过渡窗口期内尚未挂载或不可见，所有选择器都返回 None，方法直接抛出异常。

页面使用 WUI Steps 组件（`wui-steps-item-wrap`），不属于 `.ant-tabs-tab`、`.wui-tabs-tab` 或 `[role="tab"]` 等标准 tab 类名。唯一可靠的定位方式是 `[fieldid="<fieldid>"]`，而该属性由框架异步设置。

## Goals / Non-Goals

**Goals:**

- 在 `_resolve_visible_tab_action` 中增加轮询重试，等待页签元素在渲染过渡后变为可见且可点击。
- 保持 fieldid 优先的定位顺序，在重试期间持续尝试 `[fieldid]` 选择器。
- 在所有选择器耗尽后生成包含 fieldid 匹配计数和 stepBar 容器状态的诊断信息。
- 正常路径（元素已渲染）零额外延迟——首轮命中即返回。

**Non-Goals:**

- 不改变 `tab.click` 的完成信号等待逻辑（`_wait_for_action_completion`）。
- 不改变 DOM 过渡恢复逻辑（`_try_restore_previous_template_after_dom_transition`）。
- 不修改 `_tab_action_selectors` 或 `_tab_exact_text_selectors` 生成的选择器列表。
- 不为其他动作（`toolbar.click`、`query.search` 等）引入重试——它们的元素通常不经历异步挂载。

## Decisions

### D1: 在 `_resolve_visible_tab_action` 内部实现轮询，而非修改 `_find_first_visible_selector`

`_find_first_visible_selector` 被多个动作复用（工具栏、查询、行级动作等）。为它增加重试参数会影响所有调用方的行为。将轮询逻辑限制在 `_resolve_visible_tab_action` 内部可以精确控制重试范围。

**替代方案**：给 `_find_first_visible_selector` 加 `retry=True` 参数。否决——影响范围不可控，且其他动作不需要重试。

### D2: 轮询间隔 500ms，超时上限 5000ms

从历史失败报告看，失败步骤的耗时为 11.5 秒（遍历所有选择器 × 所有 frame 的一次耗时约 2-4 秒）。500ms 间隔 × 10 次重试 = 5 秒上限，加上单次遍历耗时，总等待约 7-9 秒，在 19 秒的 `tab.click` 完成等待上限内。

**替代方案**：使用 Playwright 的 `page.wait_for_selector`。否决——它只等待单个选择器，无法覆盖"先试 fieldid 再试文本"的多选择器策略，且无法复用现有的 `_is_clickable_action_target` 校验。

### D3: 增强诊断通过 `_collect_tab_diagnostic` 私有方法生成

新增一个私有方法 `_collect_tab_diagnostic(fieldid, action_label)` 返回格式化字符串，在 `click_tab_action` 的 `except RuntimeError` 分支中拼接到错误消息。包含：

- `[fieldid="<fieldid>"]` 的 count、首个匹配元素的 visible 和 bounding_box
- `[fieldid="stepBar"]` 的 count 和 `wui-steps-item-wrap` 子元素数量
- 文本匹配 `text="<action_label>"` 的 count 和首个匹配元素的 tag/class

**替代方案**：将诊断写入独立文件。否决——现有模式是在错误消息中内联诊断文本（如"导出候选 selector=..."），保持一致。

### D4: 重试循环使用 `time.monotonic()` 计时

避免使用 `page.wait_for_timeout` 作为计时器（它受 Playwright 内部调度影响），使用 Python 侧的 monotonic 时钟控制总耗时。

## Risks / Trade-offs

- **[风险] 重试增加最坏情况耗时约 5 秒** → 缓解：仅在首轮失败后进入重试；正常路径零延迟。5 秒上限在 19 秒完成等待内。
- **[风险] 页签确实不存在时（如页面错误），重试白白等待 5 秒** → 缓解：增强诊断在错误消息中明确报告 fieldid 和 stepBar 状态，帮助快速分类为页面错误而非工具问题。
- **[取舍] 不使用 Playwright 原生 `wait_for_selector`** → 代价：需要手动实现轮询循环。收益：保持与现有 `_is_clickable_action_target` 和多 frame 搜索的一致性。
