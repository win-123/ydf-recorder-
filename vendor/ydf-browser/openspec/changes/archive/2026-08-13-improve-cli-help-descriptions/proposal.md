## Why

当前 `ydf-browser --help` 和 `ydf-browser run --help` 只能列出命令与参数名称，参数没有用途、默认值、输入格式或组合约束说明。用户必须再查阅 README、测试人员指南或源码，才能判断参数如何使用；随着 `run` 的输入、并发、AI 观察、网络转发和报告选项持续增加，这种入口已经不足以支持命令行自助使用。

## What Changes

- 为顶层命令、嵌套子命令和参数补充清晰的中文帮助说明。
- 按业务用途组织 `run --help` 的参数，并说明关键默认值、输入格式、互斥关系和运行约束。
- 统一常见参数的 metavar 和描述，使 DSL 输入、环境配置、用例筛选、浏览器运行、AI 观察、请求转发和报告输出更容易理解。
- 为 root、`run`、`validate` 及其它命令的帮助输出增加回归覆盖，防止参数存在但说明缺失。
- 在面向用户的命令行文档中说明 `--help` 是参数级即时参考入口，保持文档与 CLI 语义一致。
- 不改变命令执行、退出码、报告格式或参数校验语义；`profile clear` 当前拒绝的局部清理选项不在本 change 中扩展为可用能力。

## Capabilities

### New Capabilities

- `cli-help-descriptions`: 为 ydf-browser 命令行提供完整、可操作且与当前行为一致的命令和参数帮助说明。

### Modified Capabilities

- None.

## Impact

- 主要影响 `ydf_browser/cli.py` 中的 argparse parser 定义和 CLI 帮助输出测试。
- 需要补充或调整 README、发布测试人员指南等面向用户的命令行入口说明。
- 不新增依赖，不改变运行时、DSL、报告、认证、浏览器 profile 或请求转发实现。
