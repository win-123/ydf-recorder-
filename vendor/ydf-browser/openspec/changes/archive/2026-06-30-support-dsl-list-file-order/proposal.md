## Why

批量执行真实 YonDiF 用例时，用户经常需要按人工维护的文件顺序跑一组 DSL。现在只能在命令行逐个写 `--dsl` 文件，长列表不方便复用，也容易因为复制顺序出错。

## What Changes

- 为 `run` 和 `validate` 增加文本 DSL 清单输入参数，清单中每个非空、非注释行表示一个 DSL 文件。
- 清单文件按行顺序展开为 DSL 输入，后续仍复用现有 DSL 文件发现、去重、加载、过滤和执行流程。
- 清单中的相对路径按清单文件所在目录解析，便于把清单和 DSL 文件一起移动或提交。
- 清单只排序 DSL 文件，不新增按 case code 排序能力；单个 DSL 文件内的 cases 仍按文件内顺序执行。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `dsl-run-input-order`: 增加从文本清单文件展开 DSL 输入，并按清单行顺序构造 `run` / `validate` 执行计划的要求。

## Impact

- 影响 CLI 参数解析、DSL 输入展开和运行报告元数据。
- 不影响 DSL 文件 schema、单据运行时、执行器、绑定器或 YonDiF 页面操作语义。
- 不增加新依赖，复用现有文本读取和 DSL 发现流程。
