## Why

`AGENTS.md` 已经增长到 1816 行，混合了新 agent 接手入口、历史验证结果、页面级发现、组件细节和工程技能配置。新会话需要的是少量不可违反的门禁和权威文档索引，而不是继续把一次性证据和长期知识都堆进同一个文件。

ADR `docs/adr/0001-keep-agents-md-as-thin-agent-entrypoint.md` 已明确决策：`AGENTS.md` 只保留精简入口，领域语言归 `CONTEXT.md`，稳定能力语义归 `openspec/specs/`，人类指南归 `docs/`，Matt Pocock skills 配置归 `docs/agents/`。需要用一个窄范围 OpenSpec change 固化这次清理的验收标准，避免瘦身工作变成主观编辑。

## What Changes

- 建立 `AGENTS.md` 作为薄 agent 入口的规格：目标 150-250 行，硬上限 300 行。
- 固定精简后的章节结构：Scope、Must Follow、Source Of Truth、Core Workflow、Runtime Ground Rules、Verification Gates、Useful Commands、Agent Skills。
- 要求 `AGENTS.md` 只链接权威来源，不复制页面级、组件级、历史报告或带日期的一次性证据。
- 要求清理时使用现有权威文档：`CONTEXT.md`、`docs/adr/`、`docs/agents/` 和 `openspec/specs/`。
- 不在本 change 中创建新的运行时能力，不迁移全部历史内容，也不引入额外索引系统。

## Capabilities

### New Capabilities
- `agent-entrypoint-guidance`: 约束本仓库 agent 入口文档的结构、长度、权威来源链接和历史细节清理规则。

### Modified Capabilities

## Impact

- 影响文件：`AGENTS.md`，以及必要时少量补充 `docs/` 或 `openspec/specs/` 中已经缺失的权威归宿。
- 不影响 `ydf_browser` 运行时代码、DSL 语义、CLI 参数、真实环境登录流程或浏览器执行逻辑。
- 后续实现需要验证 `AGENTS.md` 行数低于 300，结构符合 ADR，且 OpenSpec artifacts 通过结构校验和语言检查。
