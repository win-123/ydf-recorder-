## Why

YonDiF 的“设置金额单位”是跨菜单复用的公共组件，当前只能用通用点击、表单和弹窗步骤拼出交互，DSL 会暴露不必要的页面细节。

本变更提供一个独立语义，让用例只表达“把金额单位设置为元或万元”，运行时负责打开公共组件弹窗、选择 radio 并确认。

## What Changes

- 新增 `amount_unit.set` DSL 语义，目标只需要声明 `value`。
- 支持值限定为 `元` 和 `万元`。
- 运行时点击当前页面的 `LCDSetAmtunit` 公共组件按钮，打开金额单位弹窗，选择对应 radio 后点击确认。
- 不支持 `target.label` 覆盖入口按钮；入口固定为公共组件“设置金额单位”。
- 不改变现有 `toolbar.click`、`action.click`、`import.upload` 或 `import.download_template` 语义。

## Capabilities

### New Capabilities
- `amount-unit-setting`: 定义金额单位公共组件的 DSL、弹窗 radio 选择、确认和报告语义。

### Modified Capabilities

## Impact

- 影响 DSL schema、executor 分发、Playwright runtime 公共组件处理和回归测试。
- 不新增依赖，不改变现有 YAML 的兼容行为。
