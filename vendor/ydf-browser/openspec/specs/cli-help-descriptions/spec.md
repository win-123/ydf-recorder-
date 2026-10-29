# cli-help-descriptions Specification

## Purpose
让用户可以仅通过 ydf-browser 的命令行帮助输出理解命令用途、参数格式、默认值和组合约束，减少在源码与外部文档之间反复查找的成本。
## Requirements
### Requirement: 命令和选项提供可操作的帮助

`ydf-browser` 及其所有嵌套子命令的帮助输出 MUST 为列出的命令、位置参数和选项提供面向用户的说明。取值参数的说明 MUST 覆盖其用途和输入格式；有稳定默认值或使用约束时 MUST 同时说明；布尔开关 MUST 说明启用后的行为。

#### Scenario: 顶层帮助说明可用命令

- **WHEN** 用户执行 `ydf-browser --help`
- **THEN** 输出 MUST 说明 `login`、`menu`、`template`、`page`、`validate`、`doctor`、`update`、`profile`、`install-skill` 和 `run` 各自的用途，而不只显示命令名称

#### Scenario: 嵌套命令帮助说明其选项

- **WHEN** 用户执行 `ydf-browser validate --help` 或其它嵌套命令的 `--help`
- **THEN** 输出 MUST 对该命令列出的每个参数提供可操作的用途说明

### Requirement: run 帮助公开输入和执行约束

`ydf-browser run --help` MUST 说明 DSL 输入、fixture 输入、环境配置、浏览器 profile、用例筛选、并发、失败策略、性能与 AI 观察、请求转发以及报告输出参数的实际用途。说明 MUST 明确关键约束，包括 `--dsl-list` 的顺序执行限制、持久化 profile 与并发的关系、AI 观察模式的并发限制，以及 `--report-file` 与报告目录的关系。

#### Scenario: 用户可以区分 DSL 输入模式

- **WHEN** 用户查看 `ydf-browser run --help`
- **THEN** 用户 MUST 能从帮助文本区分 `--dsl`、`--dsl-list`、`--template-file`、`--runtime-file` 和 `--menu-path` 的用途、输入格式及组合方式

#### Scenario: 用户可以理解并发和观察限制

- **WHEN** 用户查看 `ydf-browser run --help`
- **THEN** 帮助文本 MUST 说明 `--concurrency` 的默认值和有效范围，并提示持久化 profile、`--dsl-list`、`--ai-observe` 对并发的限制

#### Scenario: 用户可以定位生成的报告

- **WHEN** 用户查看 `ydf-browser run --help`
- **THEN** 帮助文本 MUST 区分 `--report-dir` 的默认运行目录与 `--report-file` 的确定性报告路径，并说明相关事件文件的输出位置

### Requirement: 帮助文本符合受支持的行为

CLI 帮助文本 MUST 与当前可执行行为一致，不得把被拒绝、未实现或仅用于兼容的参数描述为可成功完成的能力。对于 `profile clear` 当前仍展示但执行时拒绝的局部清理选项，帮助文本 MUST 明确其当前不受支持，除非另一个明确变更同时调整了该行为。

#### Scenario: 不支持的 profile 清理不会被描述为可用

- **WHEN** 用户执行 `ydf-browser profile clear --help`
- **THEN** `--cookies`、`--cache` 和 `--storage`（如果仍被展示） MUST 被标记为当前不支持局部清理，且帮助 MUST 指向清空整个 profile 的实际行为

#### Scenario: 帮助不会改变命令执行

- **WHEN** 用户在不修改参数的情况下执行原有 `ydf-browser` 命令
- **THEN** 帮助说明变更 MUST NOT 改变命令的参数解析、运行结果、退出码或报告格式

### Requirement: 帮助可作为稳定的本地参考

帮助输出 MUST 使用项目既有 CLI 入口生成，不得要求额外服务、网络访问或新安装依赖。所有命令的 `--help` 请求 MUST 正常退出，并允许用户在任意子命令层级直接查看对应说明。

#### Scenario: 未配置环境时帮助仍可用

- **WHEN** 用户在未配置 YonDiF 环境或未登录的机器上执行任意支持的 `--help` 命令
- **THEN** CLI MUST 输出对应帮助并以成功状态退出，而不是尝试登录、启动浏览器或读取业务环境
