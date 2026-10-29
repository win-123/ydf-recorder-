# openspec-artifact-language Specification

## Purpose
定义本项目 OpenSpec 文档的“兼容中文”写法、解析兼容边界，以及生成后和交付前的语言检查门禁。
## Requirements
### Requirement: OpenSpec 文档必须使用兼容中文写法
系统 MUST 在本项目后续生成 OpenSpec 文档时使用“兼容中文”策略：人类可读正文、业务背景、设计说明和任务描述使用简体中文，OpenSpec CLI 解析依赖的结构标题和规范关键字保持英文。

#### Scenario: 生成 proposal 文档
- **WHEN** agent 为本项目创建 `proposal.md`
- **THEN** `## Why`、`## What Changes`、`## Capabilities` 和 `## Impact` 标题 MUST 保持英文
- **THEN** 标题下的动机、变更内容、能力说明和影响范围 MUST 使用简体中文描述

#### Scenario: 生成 delta spec 文档
- **WHEN** agent 为本项目创建 `specs/<capability>/spec.md`
- **THEN** delta 标题如 `## ADDED Requirements`、需求标题前缀 `### Requirement:` 和场景标题前缀 `#### Scenario:` MUST 保持英文
- **THEN** 需求正文 MUST 使用简体中文表达，并保留 `MUST` 或 `SHALL` 作为规范关键词
- **THEN** 场景步骤 MUST 保留 `WHEN`、`THEN` 和可选 `AND` 标记

#### Scenario: 生成 design 和 tasks 文档
- **WHEN** agent 为本项目创建 `design.md` 或 `tasks.md`
- **THEN** artifact 模板要求的 Markdown 结构 MUST 保持可被 OpenSpec workflow 识别
- **THEN** 设计背景、目标、决策、风险和任务描述 MUST 使用简体中文

### Requirement: OpenSpec 解析兼容性必须保持
项目中文化规则 SHALL NOT 要求翻译 OpenSpec CLI 当前硬编码解析的英文机器标记，以免破坏 validate、status、archive 或 apply 流程。

#### Scenario: 保留解析敏感标题
- **WHEN** agent 生成或更新 OpenSpec 文档
- **THEN** agent MUST NOT 将 `## Requirements`、`## ADDED Requirements`、`### Requirement:`、`#### Scenario:`、`## Why` 或 `## What Changes` 翻译成中文
- **THEN** 生成结果 MUST 能继续通过现有 OpenSpec CLI 解析

#### Scenario: 避免修改 OpenSpec 内部实现
- **WHEN** 落地兼容中文策略
- **THEN** 实现 SHALL 仅通过项目级 OpenSpec 配置约束生成行为
- **THEN** 实现 MUST NOT 修改 OpenSpec CLI 包、schema 解析器、归档逻辑或业务代码

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
