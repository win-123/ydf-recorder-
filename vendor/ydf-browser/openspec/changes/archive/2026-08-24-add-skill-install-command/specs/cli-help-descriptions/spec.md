## MODIFIED Requirements

### Requirement: 命令和选项提供可操作的帮助

`ydf-browser` 及其所有嵌套子命令的帮助输出 MUST 为列出的命令、位置参数和选项提供面向用户的说明。取值参数的说明 MUST 覆盖其用途和输入格式；有稳定默认值或使用约束时 MUST 同时说明；布尔开关 MUST 说明启用后的行为。

#### Scenario: 顶层帮助说明可用命令

- **WHEN** 用户执行 `ydf-browser --help`
- **THEN** 输出 MUST 说明 `login`、`menu`、`template`、`page`、`validate`、`doctor`、`update`、`profile`、`install-skill` 和 `run` 各自的用途，而不只显示命令名称

#### Scenario: 嵌套命令帮助说明其选项

- **WHEN** 用户执行 `ydf-browser validate --help` 或其它嵌套命令的 `--help`
- **THEN** 输出 MUST 对该命令列出的每个参数提供可操作的用途说明
