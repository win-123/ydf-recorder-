## Purpose

让用户直接执行 ydf-browser 时可以立即了解可用命令和下一步操作，而不是看到缺少内部参数名的 argparse 错误。

## ADDED Requirements

### Requirement: 无参数执行显示顶层帮助

用户执行 `ydf-browser` 且未提供任何参数时，CLI MUST 将顶层帮助输出到 stdout，并以退出码 0 正常结束。输出 MUST 包含用法、可用顶层命令及其用途说明。

#### Scenario: 用户直接启动 CLI

- **WHEN** 用户执行 `ydf-browser`
- **THEN** stdout MUST 包含顶层 usage、`run` 命令和命令说明
- **AND** 进程 MUST 返回退出码 0
- **AND** stderr MUST NOT 报告缺少 `command` 参数

#### Scenario: 未配置环境时直接启动 CLI

- **WHEN** 用户在未登录、未配置环境或没有可用浏览器的机器上执行 `ydf-browser`
- **THEN** CLI MUST 仍然输出顶层帮助并成功退出
- **AND** MUST NOT 登录、读取业务配置、启动浏览器或访问网络

### Requirement: 无参数帮助与显式帮助保持一致

无参数执行输出的顶层帮助 MUST 与用户执行 `ydf-browser --help` 所获得的帮助保持同一内容和说明来源，避免维护两套命令列表。

#### Scenario: 用户比较两种帮助入口

- **WHEN** 用户分别执行 `ydf-browser` 和 `ydf-browser --help`
- **THEN** 两次 stdout MUST 提供相同的顶层 usage、命令列表和参数说明

### Requirement: 显式参数错误语义保持不变

本能力 MUST 仅改变完全无参数的启动行为。未知命令、未知选项、缺少选项值和嵌套命令缺失等显式参数错误 MUST 继续返回非零退出码并由 CLI 报告错误。

#### Scenario: 用户输入未知命令

- **WHEN** 用户执行带有未知命令的 CLI 调用
- **THEN** CLI MUST 返回非零退出码并报告参数错误，而不是把该调用视为无参数帮助
