# cli-zsh-completion Specification

## Purpose
为 ydf-browser 提供与实际 CLI 声明一致的 zsh 补全，使用户通过一行配置即可发现命令、参数、固定候选值和本地路径，降低查阅帮助与手工输入的成本。

## Requirements

### Requirement: 生成可直接加载的 zsh 补全

系统 SHALL 支持 `ydf-browser completion zsh`，成功时退出码为零且 stdout 只包含可 source 的 zsh 内容，不读取环境配置、不登录、不启动浏览器、不触发后台更新。系统 MUST 拒绝不支持的 Shell 并返回非零退出码。

#### Scenario: 一行启用补全

- **WHEN** 用户在 zsh 加载 `[[ $commands[ydf-browser] ]] && source <(ydf-browser completion zsh)`
- **THEN** 系统注册 ydf-browser 补全
- **AND** 仅在缺少 `compdef` 时初始化 `compinit`，保留标准安全检查并复用已有补全环境

#### Scenario: 拒绝不支持的 Shell

- **WHEN** 用户执行 `ydf-browser completion bash`
- **THEN** 命令返回非零退出码，stdout 不输出可执行补全内容

### Requirement: 本地补全当前 CLI 声明

系统 SHALL 依据当前 CLI 声明补全顶层及嵌套子命令、当前命令的参数名和固定枚举值。系统 SHALL 为路径参数提供本地文件或目录补全，支持空格路径、重复参数、多值 `--dsl` 和 `--option=value`；不读取 DSL 或业务环境生成候选。Tab 操作 MUST 不启动 Python 或访问业务系统。

#### Scenario: 补全命令及枚举值

- **WHEN** 用户分别在 `ydf-browser menu `、`ydf-browser run --` 和 `ydf-browser run --on-case-failure ` 后按 Tab
- **THEN** 分别提供 `open`、run 的参数名，以及 `continue`、`stop_suite`、`stop_run` 候选

#### Scenario: 连续路径与后续选项

- **WHEN** 用户在 `ydf-browser run --dsl first.yaml ` 后输入另一路径前缀或参数前缀
- **THEN** 继续补全路径或当前命令参数，路径中的空格被正确引用

#### Scenario: 目录与模板来源

- **WHEN** 用户补全 `--report-dir` 或 `template fetch` 的来源
- **THEN** 前者提供目录，后者允许补全本地文件，且不查询菜单候选
