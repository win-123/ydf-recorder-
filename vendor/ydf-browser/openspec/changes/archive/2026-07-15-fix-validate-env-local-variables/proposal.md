## Why

DSL 使用环境配置变量时，`run` 能按约定解析 `env.yaml` 与 `env.local.yaml`，但 `validate` 只读取 `--vars-file` 和 `--var`，导致同一 DSL 在校验和执行阶段结果不一致。需要让静态校验复用现有变量来源与覆盖顺序，避免合法用例被误报为变量未定义。

## What Changes

- `validate` 支持选择 `--env` 和 `--config`，默认沿用现有环境配置发现规则。
- `validate` 与 `run` 复用同一变量合并逻辑，按环境配置、`--vars-file`、`--var` 的顺序覆盖。
- 增加 CLI 回归测试，证明 `env.local.yaml` 中的变量能参与校验且命令行覆盖优先级不变。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `environment-config-resolution`: 补充 `validate` 必须读取合并后的环境变量，并保持外部变量覆盖顺序的要求。

## Impact

- 影响 `ydf_browser/cli.py` 中 `validate` 参数与变量加载入口。
- 影响 `tests/test_cli.py` 中 CLI 校验回归覆盖。
- 不增加依赖，不改变 DSL 结构，也不触发真实浏览器或 YonDiF 环境访问。
