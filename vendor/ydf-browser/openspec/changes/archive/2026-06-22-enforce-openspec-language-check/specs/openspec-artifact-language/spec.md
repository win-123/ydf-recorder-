## ADDED Requirements

### Requirement: OpenSpec 文档生成后必须执行语言检查
系统 SHALL 在本项目生成或更新 OpenSpec 文档后执行语言检查门禁，确保“兼容中文”策略在最终回复前被验证，而不只依赖 agent 记忆或人工审查。

#### Scenario: 最终回复前检查新生成的文档
- **WHEN** agent 为某个 OpenSpec 变更创建或更新 `proposal.md`、`design.md`、`tasks.md` 或 `specs/**/*.md`
- **THEN** agent MUST 在最终回复前运行 `openspec validate <change> --strict`
- **AND** agent MUST 运行 `./scripts/check_openspec_language.py --change <change>` 校验该变更的 OpenSpec 文档
- **AND** 如果任一检查失败，agent MUST 先修正文档并重新检查，不能报告文档已完成

#### Scenario: 保持工具内置模板可更新
- **WHEN** 本项目需要加强 OpenSpec 文档的中文输出稳定性
- **THEN** 系统 SHALL 继续使用工具包内置 `spec-driven` schema/templates
- **AND** 系统 MUST NOT 为了语言约束同名覆盖 `openspec/schemas/spec-driven`

### Requirement: OpenSpec 交付动作前必须执行语言检查
系统 SHALL 在 OpenSpec 变更的归档、提交或推送前再次执行语言检查门禁，防止生成阶段遗漏的问题进入归档或提交历史。

#### Scenario: 归档前需要语言检查证据
- **WHEN** agent 准备归档某个 OpenSpec 变更
- **THEN** agent MUST 确认 `openspec validate <change> --strict` 已通过
- **AND** agent MUST 确认 `./scripts/check_openspec_language.py --change <change>` 已针对该变更通过
- **AND** 如果语言检查失败，agent MUST 停止归档并先修正文档

#### Scenario: 提交或推送前需要语言检查证据
- **WHEN** agent 准备提交或推送包含 OpenSpec 文档的改动
- **THEN** agent MUST 确认相关 OpenSpec 变更或主规格文件已通过项目语言检查
- **AND** agent MUST 在交付说明中报告已执行的 OpenSpec 结构校验和语言检查

### Requirement: 项目必须提供 OpenSpec 语言检查脚本
系统 SHALL 提供项目内可执行的 OpenSpec 语言检查脚本，供生成后门禁和交付前门禁复用。

#### Scenario: 按变更检查 OpenSpec 文档
- **WHEN** 用户或 agent 运行 `./scripts/check_openspec_language.py --change <change>`
- **THEN** 脚本 MUST 检查该变更下的 `proposal.md`、`design.md`、`tasks.md` 和 `specs/**/*.md`
- **AND** 脚本 MUST 在发现人读正文明显以英文为主时返回非零退出码
- **AND** 脚本 MUST 在输出中标明不合规文件和可定位的问题位置

#### Scenario: 保留 OpenSpec 机器标记和技术标识
- **WHEN** 脚本检查 OpenSpec 文档
- **THEN** 脚本 MUST 允许 `## Why`、`## What Changes`、`## ADDED Requirements`、`### Requirement:`、`#### Scenario:`、`MUST`、`SHALL`、`WHEN`、`THEN`、`AND` 等 OpenSpec 机器标记保持英文
- **AND** 脚本 MUST 允许命令、路径、文件名、代码标识符、DSL 步骤名称和测试名保持原文
- **AND** 脚本 MUST 重点检查业务背景、设计说明、需求正文、场景说明和任务描述是否使用简体中文
