## Context

`run` 已通过 `ConfigLoader` 解析目标环境，并由共享变量加载入口依次合并环境配置、变量文件和命令行变量。`validate` 当前复制了后两层合并代码，既未加载环境配置，也没有 `--env`、`--config` 参数，因此绕过了 `env.local.yaml`。

## Goals / Non-Goals

**Goals:**

- 让 `validate` 与 `run` 使用同一变量合并入口和覆盖顺序。
- 允许校验时选择环境名或显式配置文件。
- 用 CLI 回归测试锁定 `env.local.yaml` 变量与命令行覆盖行为。

**Non-Goals:**

- 不改变 DSL 变量语法、运行期捕获变量或随机变量语义。
- 不新增配置加载器、变量抽象或外部依赖。
- 不执行登录、菜单打开或真实浏览器验证。

## Decisions

1. `validate` 参数增加与 `run` 一致的 `--env` 和 `--config`。相比隐式固定读取 `ydf`，这能保持多环境和显式配置路径能力一致。
2. `_cmd_validate` 直接使用 `ConfigLoader(args.config).get_env(args.env)` 与共享的 `_load_external_variables`。相比继续复制合并循环，共享入口能一次保证环境配置、`--vars-file`、`--var` 的覆盖顺序，名称也不再暗示只服务于 `run`。
3. 回归测试从临时工作目录构造 `config/env.yaml`、`config/env.local.yaml` 和最小 DSL，并通过真实 `main()` 入口断言解析后的 suite 值；不模拟 `ConfigLoader`，避免只验证调用形式。

## Risks / Trade-offs

- `validate` 将开始读取配置文件，缺少有效默认配置时会比变量解析更早报告配置错误。通过提供 `--config` 并沿用现有默认配置发现规则，使行为与 `run` 一致且错误来源明确。
- CLI 新增两个可选参数，不影响现有无变量 DSL 或已有 `--vars-file`、`--var` 调用。
