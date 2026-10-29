## 1. 无参数帮助行为

- [x] 1.1 在 `tests/test_cli.py` 中先增加无参数调用的失败回归，断言 stdout 与显式 `--help` 一致、退出码为 0，且不会调用配置或运行时逻辑
- [x] 1.2 修改 `ydf_browser/cli.py` 的顶层 parser，使无参数调用复用现有顶层帮助并成功退出，同时保持嵌套命令和显式参数错误语义不变
- [x] 1.3 增加或调整未知命令、不完整嵌套命令的回归覆盖，确认它们仍返回非零退出码

## 2. 用户入口文档

- [x] 2.1 在 `README.md` 和 `docs/release/tester-guide.md` 的帮助入口附近说明直接执行 `ydf-browser` 也会显示顶层帮助

## 3. 验证与收尾

- [x] 3.1 运行无参数、显式 `--help` 和错误参数命令，确认输出、退出码和无副作用行为符合规格
- [x] 3.2 运行 `./.venv/bin/python -m pytest`、`openspec validate show-help-on-no-args --strict`、`./scripts/check_openspec_language.py --change show-help-on-no-args` 和 `git diff --check`
