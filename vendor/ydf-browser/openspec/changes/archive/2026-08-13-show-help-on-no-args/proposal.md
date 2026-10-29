## Why

当前用户直接执行 `ydf-browser` 时只得到 `the following arguments are required: command` 的 argparse 错误，不显示可用命令或下一步提示。工具主要面向测试人员、开发人员和 AI agent，首次启动应能直接进入可探索的帮助入口。

## What Changes

- 无参数执行 `ydf-browser` 时输出与 `ydf-browser --help` 等价的顶层帮助到 stdout。
- 无参数执行成功退出，避免把正常的命令发现行为报告为错误。
- 显式提供未知参数、缺失参数值或非法参数时继续使用现有 argparse 错误和非零退出语义。
- 增加无参数行为的 CLI 回归测试，并在用户指南中说明该入口。
- 不触发登录、配置读取、浏览器启动、网络访问或业务执行。

## Capabilities

### New Capabilities

- `no-args-help`: 用户直接运行 ydf-browser 时获得顶层命令帮助和成功退出状态。

### Modified Capabilities

- None.

## Impact

- 影响 `ydf_browser/cli.py` 的顶层参数解析分支和 `tests/test_cli.py`。
- README 与测试人员指南补充无参数启动行为说明。
- 不新增依赖，不改变已有带参数命令、报告、退出码或运行时行为。
