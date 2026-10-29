## Why

真实 DSL 在页面操作或业务断言处失败后，当前运行会立即清理浏览器页面，用户只能依据报告和静态诊断文件判断问题来源，无法核对失败当刻仍可交互的系统状态。需要一个显式、仅供人工诊断的 CLI 开关，在不改变失败结论的前提下暂时保留可检查页面。

## What Changes

- 为 `ydf-browser run` 新增 `--pause-on-failure`，在首个具有可检查页面的用例失败后停止整次运行并等待用户结束检查。
- 将该能力限定为真实、有头、串行、交互式普通 DSL 运行，并拒绝 fixture、headless、并发、AI 观察、性能采集和冲突的命令行失败策略。
- 在暂停期间保持失败页面可交互；人工操作仅用于诊断，不进入 DSL 步骤或验证证据，也不改变原失败结果。
- Enter 或用户主动关闭失败页签/浏览器后沿用现有清理流程并生成失败报告；Ctrl+C 作为外部终止清理浏览器并返回 `130`，不保证完整报告。
- 在报告计时中记录最小 `failure_pause` 信息，使人工等待与步骤执行耗时可区分。

## Capabilities

### New Capabilities

- `failure-scene-pausing`: 定义失败现场暂停的 CLI 参数、适用边界、触发条件、交互收尾、失败策略和报告记录。

### Modified Capabilities

- `browser-profile-lifecycle`: 为临时和持久化浏览器运行增加显式失败现场暂停期间延后关闭页面或上下文的例外。

## Impact

- CLI、运行编排与页面存活查询：`ydf_browser/cli.py`、`ydf_browser/runtime.py`
- 浏览器生命周期规格：`openspec/specs/browser-profile-lifecycle/spec.md`
- CLI 与运行时聚焦回归：`tests/test_cli.py`、`tests/test_runtime.py`
- 用户文档与领域词汇：CLI help、相关指南、`CONTEXT.md`
- 不新增依赖，不改变 DSL schema，不改变未启用参数时的默认行为。
