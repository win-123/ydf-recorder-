## ADDED Requirements

### Requirement: 显式 DSL 输入保留命令顺序
系统 SHALL 在 `run` 和 `validate` 命令中保留显式 `--dsl` 文件参数的出现顺序。

#### Scenario: 单个 --dsl 后包含多个文件
- **WHEN** 用户运行 `ydf-browser run --dsl b.yaml a.yaml`
- **THEN** 系统 MUST 按 `b.yaml`、`a.yaml` 的顺序构造 DSL suite 执行计划

#### Scenario: 多次传入 --dsl
- **WHEN** 用户运行 `ydf-browser run --dsl first.yaml --dsl second.yaml third.yaml`
- **THEN** 系统 MUST 按 `first.yaml`、`second.yaml`、`third.yaml` 的顺序构造 DSL suite 执行计划

### Requirement: 重复 DSL 输入保留首次位置
系统 SHALL 对解析到同一真实文件的 DSL 输入去重，并保留首次出现的位置。

#### Scenario: 同一文件出现多次
- **WHEN** 用户运行 `ydf-browser run --dsl b.yaml a.yaml b.yaml`
- **THEN** 系统 MUST 只执行一次 `b.yaml`
- **AND** 执行计划中的文件顺序 MUST 为 `b.yaml`、`a.yaml`

### Requirement: DSL 展开分组保持稳定
系统 SHALL 对目录和通配符展开出的 DSL 文件保持可复现的内部顺序。

#### Scenario: 目录输入展开文件
- **WHEN** 用户运行 `ydf-browser run --dsl suites/`
- **THEN** 系统 MUST 按稳定路径顺序展开 `suites/` 下支持的 DSL 文件

#### Scenario: 显式文件包围目录输入
- **WHEN** 用户运行 `ydf-browser run --dsl setup.yaml suites/ cleanup.yaml`
- **THEN** 系统 MUST 将 `setup.yaml` 放在目录展开结果之前
- **AND** 系统 MUST 将 `cleanup.yaml` 放在目录展开结果之后
