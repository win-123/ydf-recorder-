## ADDED Requirements

### Requirement: Text DSL list input
系统 SHALL 支持 `run` 和 `validate` 命令通过文本清单文件补充 DSL 输入，清单中每个有效行 MUST 按出现顺序展开为一个 DSL 文件输入。

#### Scenario: run 按清单文件顺序展开
- **WHEN** 用户运行 `ydf-browser run --dsl-list suites.txt`，且 `suites.txt` 依次列出 `b.yaml`、`a.yaml`
- **THEN** 系统 MUST 按 `b.yaml`、`a.yaml` 的顺序构造 DSL suite 执行计划

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

#### Scenario: 清单有效行必须指向 DSL 文件
- **WHEN** 清单文件中的有效行指向不存在的路径、目录，或不支持的文件类型
- **THEN** 系统 MUST 在业务用例执行前失败
- **AND** 错误信息 MUST 指明问题来自清单文件中的对应行
