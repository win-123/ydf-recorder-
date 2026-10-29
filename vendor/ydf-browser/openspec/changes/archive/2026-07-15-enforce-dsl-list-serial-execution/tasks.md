## 1. CLI 参数约束

- [x] 1.1 在 `tests/test_cli.py` 增加失败用例，覆盖单独使用和混合使用 `--dsl-list` 时拒绝 `--concurrency > 1`，并校验错误信息指向严格串行语义。
- [x] 1.2 在 `_cmd_run()` 加入最小的输入来源校验，使包含 `--dsl-list` 的运行只接受 `concurrency == 1`，且不改变普通 `--dsl` 的并发行为。
- [x] 1.3 运行相关 CLI 聚焦测试，确认清单默认串行、矛盾参数快速失败、普通 DSL 并发入口不回归。

## 2. 用户文档

- [x] 2.1 更新 `README.md` 和 `docs/release/tester-guide.md`，说明 `--dsl-list` 表示存在前后依赖的严格串行执行链，不能和 `--concurrency > 1` 同时使用。

## 3. 完成验证

- [x] 3.1 运行完整 `./.venv/bin/python -m pytest` 和 `git diff --check`。
- [x] 3.2 运行 `openspec validate enforce-dsl-list-serial-execution --strict` 与 `./scripts/check_openspec_language.py --change enforce-dsl-list-serial-execution`。
