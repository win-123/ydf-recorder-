## ADDED Requirements

### Requirement: 校验指令解析选中环境的变量
ydf-browser MUST 在 `validate` 加载 DSL 前读取选中环境的合并配置变量，并与其它外部变量来源使用和 `run` 相同的覆盖顺序。

#### Scenario: 当前目录本地变量参与校验
- **WHEN** 当前工作目录的 `config/env.local.yaml` 在 `environments.ydf.variables` 中声明 DSL 引用的变量，用户运行 `ydf-browser validate --dsl <path>`
- **THEN** `validate` SHALL 使用合并后的环境变量解析 DSL
- **AND** 校验 SHALL NOT 将该变量报告为未定义

#### Scenario: 校验指令尊重显式环境配置
- **WHEN** 用户运行 `ydf-browser validate --dsl <path> --env <name> --config <path>`
- **THEN** `validate` SHALL 从指定配置文件及其同目录 `env.local.yaml` 读取指定环境的变量

#### Scenario: 命令行输入覆盖环境变量
- **WHEN** 环境配置、`--vars-file` 和 `--var` 声明同一个变量
- **THEN** `validate` SHALL 按环境配置、`--vars-file`、`--var` 的顺序深度合并变量
- **AND** 后一个来源 SHALL 覆盖前一个来源的同名值
