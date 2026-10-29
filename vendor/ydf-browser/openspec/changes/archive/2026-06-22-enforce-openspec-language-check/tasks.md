## 1. 语言检查脚本

- [x] 1.1 新增 `scripts/check_openspec_language.py`，支持 `--change <change>` 并定位 `openspec/changes/<change>/proposal.md`、`design.md`、`tasks.md` 和 `specs/**/*.md`。
- [x] 1.2 实现脚本检查规则：允许 OpenSpec 机器标记、命令、路径、代码标识符、DSL step 名称和测试名保持英文，重点检查人读正文是否明显以英文为主。
- [x] 1.3 为脚本增加聚焦测试，覆盖英文正文失败、兼容中文正文通过、OpenSpec 结构标记英文通过。

## 2. 生成后门禁

- [x] 2.1 更新 `openspec/config.yaml` 的项目 context，要求生成或更新 OpenSpec artifacts 后在 final 前运行 `openspec validate <change> --strict`。
- [x] 2.2 在 `openspec/config.yaml` 的 artifact rules 中补充 `./scripts/check_openspec_language.py --change <change>` 检查要求，明确检查失败时必须先修正文档再报告完成。
- [x] 2.3 确认配置仍不要求 fork 或 override package 内置 `spec-driven` schema/templates。

## 3. 交付前门禁

- [x] 3.1 更新 `AGENTS.md`，要求 OpenSpec change 在 archive 前确认结构校验和语言检查通过。
- [x] 3.2 更新 `AGENTS.md`，要求提交或推送包含 OpenSpec artifacts 的改动前确认语言检查通过，并在交付说明中报告验证结果。
- [x] 3.3 保持规则只覆盖本次约定的前两层约束，不新增 CI、pre-commit 或 schema override。

## 4. 规格同步与验证

- [x] 4.1 将 `openspec-artifact-language` 主规格同步为语言检查脚本、生成后门禁和交付前门禁要求。
- [x] 4.2 运行脚本测试。
- [x] 4.3 运行 `openspec validate enforce-openspec-language-check --strict`。
- [x] 4.4 运行 `./scripts/check_openspec_language.py --change enforce-openspec-language-check`。
