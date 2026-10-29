## ADDED Requirements

### Requirement: Compatible Chinese OpenSpec Artifact Generation
系统 MUST 在本项目后续生成 OpenSpec artifacts 时使用“兼容中文”策略：人类可读正文、业务背景、设计说明和任务描述使用简体中文，OpenSpec CLI 解析依赖的结构标题和规范关键字保持英文。

#### Scenario: Generate a proposal artifact
- **WHEN** agent 为本项目创建 `proposal.md`
- **THEN** `## Why`、`## What Changes`、`## Capabilities` 和 `## Impact` 标题 MUST 保持英文
- **THEN** 标题下的动机、变更内容、能力说明和影响范围 MUST 使用简体中文描述

#### Scenario: Generate a delta spec artifact
- **WHEN** agent 为本项目创建 `specs/<capability>/spec.md`
- **THEN** delta 标题如 `## ADDED Requirements`、需求标题前缀 `### Requirement:` 和场景标题前缀 `#### Scenario:` MUST 保持英文
- **THEN** 需求正文 MUST 使用简体中文表达，并保留 `MUST` 或 `SHALL` 作为规范关键词
- **THEN** 场景步骤 MUST 保留 `WHEN`、`THEN` 和可选 `AND` 标记

#### Scenario: Generate design and tasks artifacts
- **WHEN** agent 为本项目创建 `design.md` 或 `tasks.md`
- **THEN** artifact 模板要求的 Markdown 结构 MUST 保持可被 OpenSpec workflow 识别
- **THEN** 设计背景、目标、决策、风险和任务描述 MUST 使用简体中文

### Requirement: OpenSpec Parser Compatibility
项目中文化规则 SHALL NOT 要求翻译 OpenSpec CLI 当前硬编码解析的英文机器标记，以免破坏 validate、status、archive 或 apply 流程。

#### Scenario: Preserve parser-sensitive headings
- **WHEN** agent 生成或更新 OpenSpec artifacts
- **THEN** agent MUST NOT 将 `## Requirements`、`## ADDED Requirements`、`### Requirement:`、`#### Scenario:`、`## Why` 或 `## What Changes` 翻译成中文
- **THEN** 生成结果 MUST 能继续通过现有 OpenSpec CLI 解析

#### Scenario: Avoid changing OpenSpec internals
- **WHEN** 落地兼容中文策略
- **THEN** 实现 SHALL 仅通过项目级 OpenSpec 配置约束生成行为
- **THEN** 实现 MUST NOT 修改 OpenSpec CLI 包、schema 解析器、归档逻辑或业务代码
