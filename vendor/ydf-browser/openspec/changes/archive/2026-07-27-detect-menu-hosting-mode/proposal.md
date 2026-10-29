## Why

YonDiF 正在将菜单主业务内容从 iframe 承载迁移为直接渲染，但现有 `ydf-browser` 只能证明菜单已打开，无法区分尚未改造和已经改造的菜单。测试人员因此缺少稳定、可批量复用的报告证据来识别需要填写 bug 单的菜单。

## What Changes

- `open_menu` 在菜单真实打开并通过页签校验后，自动识别菜单承载方式为 `iframe`、`direct` 或 `unknown`。
- 识别只关注主页面直接承载的一级业务 frame，按菜单 `service_code` 或 `service_url` 建立身份对应，并排除业务助手、弹出参照和业务页面内部的嵌套 iframe。
- `open_menu` 的结构化结果记录承载方式；`iframe` 结果同时记录菜单完整路径、`service_code`、业务 frame 名称和 URL，`unknown` 结果记录原因。
- JSON 和 HTML 报告均展示承载方式，但检测结果不改变菜单打开成功语义；不新增 DSL 动作，不自动截图或创建 bug 单。
- 使用“交易类型参数设置”和“规则管理”作为真实环境验收锚点，分别证明 `iframe` 和 `direct`。

## Capabilities

### New Capabilities

- `menu-hosting-mode-detection`: 定义菜单打开后的承载方式识别、证据输出、未知状态和报告展示语义。

### Modified Capabilities

无。

## Impact

- 运行时：`ydf_browser/runtime.py` 增加一级业务 frame 识别和证据采集。
- 执行与报告：`ydf_browser/executor.py` 的 `open_menu` 结果增加结构化承载方式，并在成功消息中展示结果。
- 测试：补充运行时分类、执行结果和报告展示的聚焦测试，并运行两个真实菜单用例。
- 领域文档：`CONTEXT.md` 增加“菜单承载方式”术语。
- 不新增第三方依赖，不改变 DSL schema，不接入缺陷平台。
