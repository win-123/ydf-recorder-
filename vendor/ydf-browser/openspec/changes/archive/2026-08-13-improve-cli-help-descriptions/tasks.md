## 1. 完善 CLI 帮助定义

- [x] 1.1 在 `ydf_browser/cli.py` 的现有 argparse parser 上补充顶层命令、嵌套子命令、位置参数和选项的中文 `description/help`，保持现有参数名、类型、默认值和解析行为不变
- [x] 1.2 为 `run` 参数增加输入、环境与浏览器、筛选、执行、性能与 AI 观察、请求转发、报告等语义分组，并为 DSL、变量、窗口尺寸和转发规则使用清晰的 metavar
- [x] 1.3 在帮助文本中准确表达 `--dsl-list`、持久化 profile、`--concurrency`、`--ai-observe`、报告路径和 fixture 参数的组合约束，并明确 `profile clear` 局部清理选项当前不受支持

## 2. 增加 CLI 帮助回归

- [x] 2.1 在 `tests/test_cli.py` 中覆盖顶层、`run`、`validate`、`profile clear` 帮助输出，断言命令说明、关键参数说明、默认值/约束和不支持参数提示存在
- [x] 2.2 保持测试不依赖完整 argparse 排版快照，并运行 CLI 聚焦测试确认帮助请求不触发登录、浏览器或环境访问

## 3. 更新用户入口文档

- [x] 3.1 在 `README.md` 增加查看顶层、`run` 和 `validate` 参数帮助的短入口，保留现有典型命令示例
- [x] 3.2 在 `docs/release/tester-guide.md` 增加面向测试人员的 `--help` 使用提示，避免复制完整参数矩阵

## 4. 完成验证

- [x] 4.1 使用当前源码入口运行所有相关 `--help` 命令，确认输出包含说明且退出码为 0，并运行 `git diff --check`
- [x] 4.2 运行 `./.venv/bin/python -m pytest`、`openspec validate improve-cli-help-descriptions --strict` 和 `./scripts/check_openspec_language.py --change improve-cli-help-descriptions`
