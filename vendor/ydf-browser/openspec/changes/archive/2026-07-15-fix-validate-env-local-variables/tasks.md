## 1. 回归测试

- [x] 1.1 在 `tests/test_cli.py` 增加真实 CLI 入口测试，构造 `env.yaml`、`env.local.yaml` 和变量 DSL，证明修复前 `validate` 无法解析本地环境变量。

## 2. 最小实现

- [x] 2.1 为 `validate` 增加 `--env`、`--config` 参数，并复用 `ConfigLoader` 与 `_load_external_variables`。
- [x] 2.2 运行聚焦测试，确认环境变量、`--vars-file`、`--var` 的覆盖顺序正确。

## 3. 交付验证

- [x] 3.1 运行 `openspec validate fix-validate-env-local-variables --strict` 和语言检查。
- [x] 3.2 运行完整 `./.venv/bin/python -m pytest` 与 `git diff --check`。
