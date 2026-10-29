## Context

真实运行中同时存在两个可见 `fieldid=proName` 输入：DOM 第一个位于旧 drawer，`receives_pointer=false`；第二个位于当前 drawer，`receives_pointer=true`。`_resolve_visible_locator()` 与 `_resolve_foreground_form_field_root()` 都按 DOM 顺序返回第一个可见实例，且 `fill_form_field()` 在既有绑定已标记 `in_dialog=true` 时跳过前景重解析，最终把值写入旧实例。

## Goals / Non-Goals

**Goals:**

- 在表单录入前从同身份候选中选择可接收 pointer 的当前实例。
- 已标记 `in_dialog=true` 的绑定也必须重新解析当前前景实例。
- 保持无冲突字段、DSL 和现有写后确认行为。

**Non-Goals:**

- 不修复 `form.assert_values` 的页面文本回退误读。
- 不改变普通文本字段的输入事件或增加重试。
- 不增加菜单、模板、字段名或 `fieldid` 特例。
- 不增加可配置重试、退避策略或新依赖。

## Decisions

### 在表单字段根解析中优先可接收 pointer 的实例

新增表单专用的同身份候选解析：复用候选 `key`、`fieldid` 和 `data_field` 生成的现有身份 selector，遍历可见实例，并用现有 `_receives_pointer_events()` 检查真实输入控件。第一个可接收 pointer 的实例立即胜出；没有命中时继续现有前景和标签回退。

替代方案一是修改全局 `_resolve_visible_locator()`，会影响工具栏、表格、树和弹出参照，范围过大。替代方案二是按 drawer 的 DOM 顺序或 z-index 排名，但真实证据已经提供更直接的可交互性判据。表单专用 pointer 解析是最小共享修复。

### 每次表单录入都重新解析当前实例

`in_dialog=true` 只说明捕获绑定时位于弹层，不能证明动态抽屉切换后仍是当前实例。因此除 runtime-only 特殊字段外，`fill_form_field()` 每次都先尝试 pointer 可交互实例，再进入现有前景、精确绑定和标签回退链路。

### 保留现有录入和确认语义

选中正确根节点后继续复用 `_resolve_fill_locator_from_root()`、`_set_text_field_value()` 和 `_confirm_plain_field_value()`；不新增等待、补写、事件分支或 DSL 字段。

## Risks / Trade-offs

- [输入中心点被装饰元素覆盖] → 复用现有 pointer 判定对节点与命中元素的包含关系，不要求命中元素必须等于 input。
- [没有候选可接收 pointer] → 保留现有前景和标签回退，避免破坏只读展示或特殊组件。
- [全局定位行为不一致] → 本 change 只修改表单字段入口，不扩散到其它组件。
