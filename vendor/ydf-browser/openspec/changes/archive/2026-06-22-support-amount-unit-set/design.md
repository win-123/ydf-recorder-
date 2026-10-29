## Context

`设置金额单位` 在模板中表现为 `LCDSetAmtunit` 公共组件，入口按钮固定显示为“设置金额单位”。点击后页面弹出一个小对话框，用户只能在 `元` 和 `万元` 两个 radio 选项中选择，再点击确认完成交互。

现有 DSL 可以用 `toolbar.click` 打开该按钮，但后续 radio 选择和确认需要拆成通用步骤，暴露了公共组件内部细节。这个组件和导入组件类似，跨菜单行为一致，适合收敛成独立语义。

## Goals / Non-Goals

**Goals:**

- 新增 `amount_unit.set`，用 `target.value` 表达目标金额单位。
- 入口固定为当前页面的 `LCDSetAmtunit` 公共组件，不支持 `target.label` 覆盖。
- 运行时完成打开弹窗、选择 `元` 或 `万元`、确认关闭。
- 报告中记录目标单位和实际选择结果，失败时保留可诊断信息。

**Non-Goals:**

- 不修复或兼容误写的 `component: action` 用法。
- 不改变 `toolbar.click` 的“更多”展开能力。
- 不支持除 `元`、`万元` 之外的金额单位。
- 不把该能力泛化成新的任意 radio 弹窗 DSL。

## Decisions

1. 新增独立 DSL 组件 `amount_unit.set`。

   备选方案是继续组合 `toolbar.click`、`form.fill`、`dialog.confirm`。组合方式代码少，但每个用例都要知道公共组件内部结构，且弹窗字段不来自当前模板。独立语义更符合现有 `import.upload`、`import.download_template` 的公共组件处理方式。

2. DSL target 只接受 `value`。

   入口按钮在公共组件中是固定语义，支持 `label` 会让用例误以为可以绑定任意工具栏按钮。保持一个字段能减少 schema 和执行分支。

3. Runtime 通过组件身份优先定位入口。

   执行器应把当前 manifest actions 传给 runtime，runtime 优先查找 `component_name=LCDSetAmtunit` 或等价模板节点，再点击其运行时可见按钮。只有组件身份不可用时，才允许按固定文本“设置金额单位”作为诊断性兜底。

4. 弹窗 radio 选择限定在前景弹窗内。

   `元` 和 `万元` 这类短文本可能出现在表格、输入框单位后缀或背景页面。运行时必须在可见金额单位弹窗范围内查找 radio 选项，不能退回全页面裸文本点击。

## Risks / Trade-offs

- [Risk] 不同页面的公共组件弹窗 DOM class 可能不完全一致 -> Mitigation: 选择器覆盖常见 modal/dialog 容器，并以可见前景层为作用域。
- [Risk] 页面背景也包含大量 `元` 文本 -> Mitigation: radio 查找必须限定在弹窗内，并优先匹配 radio wrapper 或 radio input 对应标签。
- [Risk] 弹窗打开后未识别到确认按钮 -> Mitigation: 步骤失败并报告弹窗文本和截图，而不是假定成功。
