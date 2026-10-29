## Context

字段真实存在且可编辑，但表单内部滚动区域在字段上方截止。现有扫描仅将控件矩形与窗口求交，再以该交集采样 `elementFromPoint`，因此会采到滚动区域以外的固定底栏。binder 将 `pointer_receivable=False` 排除，executor 刷新绑定后仍报身份不兼容；浏览器实际录入中的自动滚动尚未执行。

同一真实业务记录在 `1707x825` 视口复现，在较高视口通过。Windows 报告与本机模板字段身份、布局参数一致；显示缩放与窗口尺寸会改变是否落入该边界，但不是平台身份冲突。

## Goals / Non-Goals

目标是让可滚动祖先裁剪的唯一表单输入复用现有未知 pointer 状态绑定和自动滚动录入，同时保留真实遮挡及多实例歧义的失败关闭行为。

本次不新增 DSL 字段、全页面滚动步骤、Windows 分支、字段名称特例、依赖或配置；不修改 binder 的候选收敛规则。

## Decisions

DOM 扫描按原生包含块链判断实际裁剪：普通流元素沿父元素上溯，绝对及固定定位元素使用 `offsetParent`，跳过不参与其裁剪的中间 DOM 祖先。固定元素以视口为包含块时，不套用普通 DOM 祖先的滚动范围；存在变换等包含块时仍纳入该包含块的裁剪。采用平台属性，避免维护 CSS 属性白名单。

扫描分别记录当前可见交集与滚动后可能到达的区域。`auto/scroll` 且对应轴存在实际滚动范围时，可能到达区域扩展为滚动口；`hidden/clip` 等不按本规则恢复的裁剪只收窄可能到达区域。若后者为空，直接判定不可达；否则当前可见交集为空时保持未知。这样内层 `clip` 完全裁掉输入仍失败，而内层滚动口可以把输入移入外层裁剪范围时保持可恢复。

内容边界使用 `clientLeft/clientTop/clientWidth/clientHeight` 并按 `getBoundingClientRect()` 与 `offsetWidth/offsetHeight` 的比例转换到视口坐标，覆盖轴对齐缩放和 CSS `zoom`。无布局盒的 `inline/contents` 祖先不作为 overflow 裁剪口。旋转或斜切的精确多边形裁剪不在本次范围内。

不在扫描时滚动整个页面：扫描覆盖多个组件和 frame，主动滚动会改变其它候选的上下文。未知状态仍交给现有唯一身份绑定，实际录入负责滚动并确认值。文本录入必须先完成真实点击校验；点击失败直接传播，不能进入 `fill()` 或 DOM 原生赋值兜底。点击已成功但键盘录入失败时，保留现有 `fill()` 兼容路径。该共享入口也用于自由输入参照和可编辑表格文本，聚焦测试与原始用例覆盖这些相邻路径。

定位与裁剪规则依据 [CSS Overflow](https://www.w3.org/TR/CSS2/visufx.html#overflow)、[CSS Positioned Layout](https://www.w3.org/TR/css-position-3/#def-cb) 和 [CSS Transforms](https://www.w3.org/TR/css-transforms-1/#transform-rendering)，并通过当前 Chromium 的原生包含块行为核对。

## Risks / Trade-offs

共享扫描也用于字段值观察，需覆盖横纵滚动、frame、部分可见、不可滚动裁剪及真正遮挡。未知状态仍不能证明业务录入成功，因此真实 DSL 必须包含 `form.assert_values`。真实用例固定数据缺失时保留失败，不自动换行或换数据。

## Migration Plan

先加入真实浏览器失败回归，再修改扫描；运行聚焦测试、原用例和最小真实 DSL，最后运行完整 pytest、OpenSpec 结构与语言校验。回退扫描修改即可恢复原行为，无数据迁移。

## Open Questions

Windows 的实际缩放比例未由报告记录；已通过本机视口复现相同错误，不依赖该比例作为实现条件。
