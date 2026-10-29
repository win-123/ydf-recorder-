## Why

当前项目已经在 `openspec/config.yaml` 中要求 OpenSpec artifacts 使用“兼容中文”写法，但该要求仍属于生成提示，`openspec validate` 不会检查正文语言。实际流程中已多次出现生成结果正文为英文、需要人工再次要求改回中文的情况，因此需要把语言检查纳入生成后和交付前的必跑门禁。

## What Changes

- 在 OpenSpec 生成流程约束中补充语言检查命令：生成或更新 artifacts 后，final 前必须运行 `openspec validate <change> --strict` 和项目语言检查脚本。
- 在 agent 接手规则中补充交付门禁：OpenSpec change 在 archive、commit 或 push 前必须再次确认语言检查通过。
- 新增项目语言检查脚本 `scripts/check_openspec_language.py`，为上述门禁提供可执行检查入口。
- 不 fork 或 override package 内置 `spec-driven` schema/templates，避免本地模板遮蔽工具升级。
- 不在本次引入 CI 硬门禁，CI 可作为后续独立增强。

## Capabilities

### New Capabilities

### Modified Capabilities
- `openspec-artifact-language`: 补充生成后语言检查和交付前语言检查的流程要求，确保“兼容中文”规则不只停留在提示层。

## Impact

- 影响文件：`openspec/config.yaml`、`AGENTS.md`、`openspec/specs/openspec-artifact-language/spec.md`、`scripts/check_openspec_language.py`。
- 影响流程：后续 `/opsx:propose`、手动更新 OpenSpec artifacts、archive、commit 和 push 前的本地验证步骤。
- 不影响 ydf-browser 运行时代码、OpenSpec CLI package、package 模板或本地 schema 解析顺序。
