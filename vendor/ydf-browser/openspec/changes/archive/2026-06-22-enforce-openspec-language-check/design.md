## Context

本项目已经通过 `openspec/config.yaml` 为 OpenSpec artifacts 配置“兼容中文”规则：正文使用简体中文，OpenSpec 解析依赖的标题、前缀和关键字保持英文。实际使用中仍出现多次 artifacts 正文被生成成英文的情况，说明当前规则只作为 agent 生成提示，不构成可执行门禁。

OpenSpec 当前没有项目级 post-generate hook。package 内置 schema/templates 和本地安装的 skill 副本都会随工具更新而刷新；如果项目同名 override `spec-driven` schema，则会遮蔽 package 更新，不适合只为语言偏好做轻量约束。因此本次需要提供项目内语言检查脚本，再通过 config 和 AGENTS 把脚本纳入 agent 必跑流程。

## Goals / Non-Goals

**Goals:**
- 让 agent 在生成或更新 OpenSpec artifacts 后必须运行语言检查脚本，并在失败时先修正文档。
- 让 agent 在 archive、commit 或 push 前再次确认 OpenSpec 结构校验和语言检查通过。
- 新增 `scripts/check_openspec_language.py`，支持按 change 检查 OpenSpec artifacts 的中文化合规性。
- 保持 package 内置 `spec-driven` schema/templates 可随工具更新，不引入项目本地同名 override。
- 将要求写入项目可追溯的 OpenSpec artifact language 规格和接手规则。

**Non-Goals:**
- 不新增 CI、pre-commit 或其他机器强制入口。
- 不修改 OpenSpec CLI package、内置 schema/templates 或本地安装的 OpenSpec skill 副本。
- 不批量翻译历史主规格或归档 change。

## Decisions

1. 在 `openspec/config.yaml` 中增加生成后检查规则。
   - 理由：该文件会注入后续 artifact instructions，是约束 `/opsx:propose`、手动创建 artifacts 和继续生成流程的现有入口。
   - 替代方案：修改本地 skill 副本。这个方案短期有效，但 `openspec update` 可能覆盖本地 skill，维护成本和漂移风险更高。

2. 在 `AGENTS.md` 中增加交付前门禁。
   - 理由：`AGENTS.md` 是后续新会话 agent 接手本仓库时最先看到的项目规则，适合约束 archive、commit 和 push 前的验证动作。
   - 替代方案：只依赖 `openspec/config.yaml`。该方案覆盖生成 instructions，但对用户直接要求“提交/推送”的场景不够显眼。

3. 新增项目脚本 `scripts/check_openspec_language.py`。
   - 理由：OpenSpec CLI 的 `validate` 只校验结构，不校验自然语言；脚本提供可重复执行的本地门禁入口。
   - 检查范围：`--change <change>` 检查对应 change 下的 `proposal.md`、`design.md`、`tasks.md` 和 `specs/**/*.md`。
   - 检查边界：允许 OpenSpec 机器标记、命令、路径、代码标识符、DSL step 名称和测试名保留英文；重点识别人读正文和任务描述是否明显以英文为主。
   - 替代方案：只靠人工 review。该方案已经在历史流程中反复漏掉英文正文，不足以作为门禁。

4. 不 fork 或 override `spec-driven` schema。
   - 理由：project-local schema 会优先于 package schema，适合定制工作流，不适合只为中文正文约束遮蔽 package 模板更新。
   - 替代方案：创建 `spec-driven-zh`。这个方案能提高模板级引导，但会引入独立 schema 选择和升级对齐问题，本次不采用。

5. 暂不引入 CI 门禁。
   - 理由：用户本次只要求增加前两层约束，即生成流程门禁和归档/提交前门禁。CI 可作为后续更硬的独立增强。

## Risks / Trade-offs

- [Risk] 没有 CI 时，非 agent 或跳过项目流程的人仍可能提交不合规 artifacts。Mitigation: 本次先把 agent 流程约束收紧，后续如仍复发再增加 CI 或 pre-commit。
- [Risk] 语言检查脚本可能误报命令、路径或 OpenSpec 结构标记中的英文。Mitigation: 脚本检查时显式豁免机器标记、代码块、行内代码、路径和常见技术标识，只把人读正文作为重点。
- [Risk] 规则过多可能让 agent final 前验证步骤变长。Mitigation: 只要求对相关 change 或相关 OpenSpec 文件运行检查，不要求每次全仓扫描。

## Migration Plan

1. 新增 `scripts/check_openspec_language.py`，支持 `--change <change>`。
2. 更新 `openspec/config.yaml`，在 artifacts 生成规则中要求 final 前运行 `openspec validate <change> --strict` 和 `./scripts/check_openspec_language.py --change <change>`。
3. 更新 `AGENTS.md`，在 OpenSpec archive、commit、push 前要求执行并报告语言检查。
4. 更新 `openspec-artifact-language` 规格，记录脚本、生成后门禁和交付前门禁要求。
5. 使用 `openspec validate enforce-openspec-language-check --strict` 验证本 change 可解析。

## Open Questions

- 后续是否需要将同一语言检查纳入 CI 或 pre-commit，作为第三层机器强制门禁。
