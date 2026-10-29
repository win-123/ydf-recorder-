## Why

开发人员验证本地代码时，需要保留现有请求转发和登录能力，但有时希望亲自操作页面，而不是先编写 DSL 用例。当前 `run` 强制要求 DSL 输入，无法只启动一个已登录且保持转发的可见浏览器会话。

## What Changes

- 为 `ydf-browser run` 增加无 `--dsl`、无 `--dsl-list` 时的手工浏览器会话模式。
- 手工会话使用环境级凭据完成现有 API 登录，打开解析后的 `base_url/` 首页，并保持请求转发能力。
- 手工会话允许用户操作多个浏览器标签页，直到 browser context 中没有页面后正常退出。
- 手工会话不创建 DSL 测试集、用例、执行报告或新的转发证据文件格式。
- 无 DSL 时拒绝 `--headless` 以及 DSL 过滤、fixture、报告、性能和 AI 观察参数；空或无效的 `--dsl-list` 仍按 DSL 输入错误处理。
- 正常关闭输出最小手工会话结果；启动失败沿用非零错误语义，`Ctrl-C` 返回用户中断状态。

## Capabilities

### New Capabilities

- `manual-browser-session`: 定义无 DSL 登录、首页打开、请求转发、可见浏览器保持和用户控制退出的语义。

### Modified Capabilities

无。现有 profile、配置和请求转发能力被手工会话复用，但其既有要求不改变。

## Impact

- 影响 `ydf_browser/cli.py` 的 `run` 参数分流和手工会话生命周期。
- 复用 `ydf_browser/runtime.py` 的 Playwright、Cookie 注入、profile 和请求转发实现。
- 增加 CLI 单元测试、手工会话运行说明和 OpenSpec capability spec。
- 不新增第三方依赖，不改变已有 DSL 运行和 `validate` 语义。
