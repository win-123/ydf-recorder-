## Why

保存并签章后，关闭页面的确认框可能晚于工具栏动作返回才出现。弹窗按钮入口只扫描一次，导致真实按钮随后已可点击，用例仍报未找到按钮。

## What Changes

- 弹窗点击在有限时间内轮询既有按钮定位逻辑，按钮可点击后立即继续。
- 保留超时失败、弹窗作用域、主页面与子 frame 和下载处理。
- 补延迟弹窗回归及真实保存并签章用例。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `runtime-action-completion-signals`：明确弹窗按钮延迟就绪的等待与失败边界。

## Impact

影响 runtime 弹窗点击入口、相关测试和使用文档。不增加 DSL 字段、依赖或页面专用分支。
