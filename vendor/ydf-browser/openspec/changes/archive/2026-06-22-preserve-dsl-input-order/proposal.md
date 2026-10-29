## Why

`ydf-browser run --dsl xxx.yaml yyy.yaml zzz.yaml` 这种显式多文件输入应按用户在命令行中写出的顺序执行，便于测试人员控制前置数据、清理用例和回归套件顺序。当前文件发现阶段会按路径字符串全局排序，显式参数顺序会被打乱，行为和命令行直觉不一致。

## What Changes

- 保留 `--dsl` 参数展开后的显式输入顺序，多个文件按参数出现顺序进入执行计划。
- 多次传入 `--dsl` 时，按每次参数在命令行中出现的顺序合并。
- 目录输入和通配符输入内部仍保持稳定排序，保证批量发现结果可复现。
- 重复指向同一个 DSL 文件时仍只执行一次，并保留首次出现的位置。
- `validate --dsl` 使用同一文件发现规则，避免验证顺序和运行顺序不一致。

## Capabilities

### New Capabilities
- `dsl-run-input-order`: 约束 `run` 和 `validate` 在发现、去重和展开 DSL 文件时如何保留用户输入顺序。

### Modified Capabilities
- 无。

## Impact

- 影响 `ydf_browser/runner.py` 的 DSL 文件发现顺序和相关单元测试。
- 影响 `ydf_browser/cli.py` 使用发现结果构造验证列表和运行 suite specs 的顺序，但不改变 CLI 参数格式。
- 不新增依赖，不改变 DSL schema，不改变真实浏览器执行逻辑。
