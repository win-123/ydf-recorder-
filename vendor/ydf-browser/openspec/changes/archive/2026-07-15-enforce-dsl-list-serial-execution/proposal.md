## Why

`--dsl-list` 的来源是按清单顺序执行存在前后依赖的 DSL 用例，但当前实现只保证执行计划顺序，仍允许 `--concurrency > 1` 让后续用例提前启动。这会使清单看似有序、实际却破坏依赖关系，需要让参数约束与用户语义一致。

## What Changes

- 将 `--dsl-list` 明确定义为严格串行的 DSL 执行链，清单中的后续 DSL 只有在前序 DSL 全部用例完成后才可开始。
- **BREAKING**：`run` 输入中只要出现 `--dsl-list`，显式设置 `--concurrency > 1` 就在加载和执行业务用例前失败，并提示使用 `--concurrency 1`。
- `--dsl-list` 与 `--dsl` 混用时沿用同一限制，避免产生部分串行、部分并行的隐含语义。
- 不改变仅使用 `--dsl`、目录或通配符输入时的既有并发能力。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `dsl-run-input-order`: 将清单顺序从执行计划顺序收紧为严格完成顺序，并定义与 `--concurrency` 的互斥约束。

## Impact

- 影响 `ydf_browser/cli.py` 的 `run` 参数组合校验和对应 CLI 测试。
- 影响 `dsl-run-input-order` 规格、README 和发布测试指南中的参数说明。
- 不改变 runner 并发调度实现、DSL schema、执行器、运行时或第三方依赖。
