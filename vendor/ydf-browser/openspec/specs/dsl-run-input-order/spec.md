# dsl-run-input-order Specification

## Purpose
定义 `run` 和 `validate` 命令解析多个 `--dsl` 输入时的文件发现、展开、去重和执行计划顺序，确保显式文件参数按用户命令行顺序生效，同时保持目录和通配符展开结果稳定。
## Requirements
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

### Requirement: Text DSL list input
系统 SHALL 支持 `run` 和 `validate` 命令通过文本清单文件补充 DSL 输入，清单中每个有效行 MUST 按出现顺序展开为一个 DSL 文件输入。`run` 使用清单时 MUST 将展开后的全部 suite 和 case 作为严格串行依赖链执行，且 MUST 拒绝与该语义冲突的并发参数。

#### Scenario: run 按清单文件顺序展开
- **WHEN** 用户运行 `ydf-browser run --dsl-list suites.txt`，且 `suites.txt` 依次列出 `b.yaml`、`a.yaml`
- **THEN** 系统 MUST 按 `b.yaml`、`a.yaml` 的顺序构造 DSL suite 执行计划
- **AND** 系统 MUST 在 `b.yaml` 的全部 case 完成后才启动 `a.yaml` 的第一个 case
- **AND** 每个 DSL 内的 case MUST 按文件内顺序逐个完成

#### Scenario: validate 按清单文件顺序展开
- **WHEN** 用户运行 `ydf-browser validate --dsl-list suites.txt`，且 `suites.txt` 依次列出 `b.yaml`、`a.yaml`
- **THEN** 系统 MUST 按 `b.yaml`、`a.yaml` 的顺序输出可校验 DSL 文件结果

#### Scenario: 忽略空行和注释行
- **WHEN** 清单文件包含空行、只包含空白字符的行，或以 `#` 开头的注释行
- **THEN** 系统 MUST 忽略这些行
- **AND** 系统 MUST 只按剩余有效行构造 DSL 输入

#### Scenario: 相对路径按清单目录解析
- **WHEN** 用户运行 `ydf-browser run --dsl-list plans/suites.txt`，且清单中包含 `cases/a.yaml`
- **THEN** 系统 MUST 将该行解析为 `plans/cases/a.yaml`

#### Scenario: 清单输入复用普通 DSL 去重规则
- **WHEN** 清单文件多次列出同一个真实 DSL 文件
- **THEN** 系统 MUST 沿用普通 DSL 输入去重规则，只保留该文件首次出现的位置

#### Scenario: 清单输入可以和显式 DSL 输入组合
- **WHEN** 用户运行 `ydf-browser run --dsl setup.yaml --dsl-list suites.txt --dsl cleanup.yaml`
- **THEN** 系统 MUST 按 `setup.yaml`、清单有效行、`cleanup.yaml` 的顺序构造 DSL suite 执行计划
- **AND** 系统 MUST 按该完整计划严格逐个完成所有 case

#### Scenario: 清单有效行必须指向 DSL 文件
- **WHEN** 清单文件中的有效行指向不存在的路径、目录，或不支持的文件类型
- **THEN** 系统 MUST 在业务用例执行前失败
- **AND** 错误信息 MUST 指明问题来自清单文件中的对应行

#### Scenario: run 拒绝清单并发执行
- **WHEN** 用户运行 `ydf-browser run --dsl-list suites.txt --concurrency 2`
- **THEN** 系统 MUST 在加载和执行业务用例前失败
- **AND** 错误信息 MUST 说明 `--dsl-list` 仅支持 `--concurrency 1`

#### Scenario: 混合输入同样拒绝并发执行
- **WHEN** 用户运行 `ydf-browser run --dsl setup.yaml --dsl-list suites.txt --concurrency 2`
- **THEN** 系统 MUST 在加载和执行业务用例前失败
- **AND** 错误信息 MUST 说明只要使用 `--dsl-list` 就必须将 `--concurrency` 设为 1

#### Scenario: 普通 DSL 输入保留并发能力
- **WHEN** 用户运行 `ydf-browser run --dsl suites/ --no-persistent-profile --concurrency 2` 且未使用 `--dsl-list`
- **THEN** 系统 SHALL 保持现有并发调度语义
