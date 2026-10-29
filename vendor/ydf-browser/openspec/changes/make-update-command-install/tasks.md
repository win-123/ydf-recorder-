## 1. CLI 契约测试

- [x] 1.1 在现有 update CLI 测试 seam 增加无参数 update 的失败测试，断言它请求 force 检查且 install=true，并运行该单文件测试确认先红
- [x] 1.2 增加 update --check、update rollback、冲突参数和结果退出码测试，断言成功/失败/locked 的 JSON 与退出行为
- [x] 1.3 增加 YDF_BROWSER_AUTO_UPDATE=0 下显式 update 仍调用前台更新器的测试，并运行聚焦 CLI/updater 测试确认测试契约

## 2. CLI 实现

- [x] 2.1 修改 update 命令帮助和默认分派，使无参数 update 复用现有 UpdateManager 的 force 检查和安装路径，并保持 --check 只读、rollback 回滚
- [x] 2.2 在 CLI 分派层拒绝 --check 与 rollback 的组合，保留现有 JSON 输出、locked/failed 非零退出和 no_update/installed 零退出语义
- [x] 2.3 运行聚焦 CLI/updater 测试与 compileall 检查，确认实现通过且没有新增更新抽象或后台入口分支

## 3. 用户文档与 OpenSpec

- [x] 3.1 更新 README.md、docs/release/auto-update.md、docs/release/tester-guide.md 和相关 changelog，明确 update 会安装、--check 只读、手动命令绕过后台开关及下次启动生效
- [x] 3.2 校验 explicit-runtime-update-command 规格、设计与任务清单和用户可见帮助保持一致，并运行 openspec validate make-update-command-install --strict
- [x] 3.3 运行 ./scripts/check_openspec_language.py --change make-update-command-install，修复任何规格语言或结构问题

## 4. 完整验证与交付

- [x] 4.1 运行 ./.venv/bin/python -m pytest -q tests/test_update_cli.py tests/test_updater.py tests/test_cli_completion.py tests/test_package_release.py，并确认聚焦更新与安装入口测试通过
- [x] 4.2 运行 ./.venv/bin/python -m pytest -q，确认完整测试集通过
- [x] 4.3 运行 git diff --check，并检查 git diff 只包含本 change、CLI、文档和必要测试文件
- [x] 4.4 以 Issue #20 和本 OpenSpec change 为 spec 来源执行 code-review，修复 Standards/Spec 发现后重新验证
