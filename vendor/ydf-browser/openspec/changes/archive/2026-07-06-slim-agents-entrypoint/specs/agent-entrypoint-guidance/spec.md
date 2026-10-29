## ADDED Requirements

### Requirement: AGENTS.md 必须作为薄 agent 入口
本仓库 SHALL 将 `AGENTS.md` 维护为新 agent 的精简入口，而不是长期历史知识库。

#### Scenario: 入口文件保持硬行数上限
- **WHEN** 维护者或 agent 更新 `AGENTS.md`
- **THEN** `AGENTS.md` MUST 不超过 300 行
- **AND** SHOULD 保持在 150-250 行目标范围内

#### Scenario: 入口文件使用稳定章节结构
- **WHEN** `AGENTS.md` 被精简或后续维护
- **THEN** 文件 MUST 包含 Scope、Must Follow、Source Of Truth、Core Workflow、Runtime Ground Rules、Verification Gates、Useful Commands、Agent Skills 这些章节
- **AND** 每个章节 MUST 只承载新 agent 接手所需的索引、门禁或跨任务规则

### Requirement: AGENTS.md 必须链接权威来源而不是复制长期知识
本仓库 SHALL 将领域术语、稳定能力语义、人类指南和工程技能配置维护在各自权威来源中，并从 `AGENTS.md` 链接引用。

#### Scenario: 领域和技能知识使用现有归宿
- **WHEN** `AGENTS.md` 需要指向领域语言、架构决策或工程技能配置
- **THEN** 文件 MUST 链接 `CONTEXT.md`、`docs/adr/`、`docs/agents/` 或相关 `openspec/specs/`
- **AND** MUST NOT 在入口正文中复制这些来源已经覆盖的详细内容

#### Scenario: 稳定能力语义进入 OpenSpec
- **WHEN** 某条规则描述 DSL、绑定、运行时或组件行为的稳定验收语义
- **THEN** 该规则 SHOULD 放入或链接到对应 `openspec/specs/` 能力规格
- **AND** `AGENTS.md` SHOULD 只保留能防止 agent 走错主流程的摘要或链接

### Requirement: AGENTS.md 必须清除一次性和页面级历史细节
本仓库 SHALL 避免在 `AGENTS.md` 中保留容易过期的页面级发现、组件级细节和一次性证据。

#### Scenario: 删除过期运行证据
- **WHEN** 清理 `AGENTS.md` 中的历史运行信息
- **THEN** 文件 MUST NOT 保留旧测试数量、`/tmp` 报告路径、报告目录 ID、截图路径或带日期的“最近一次验证”声明作为正文事实
- **AND** 如仍需追溯证据，MUST 使用 release notes、reports、issues、changes 或其他权威记录链接

#### Scenario: 保留跨任务运行时 ground rules
- **WHEN** 某条规则会反复影响真实 DSL 诊断或执行结果
- **THEN** `AGENTS.md` MAY 保留简短 ground rule
- **AND** 该规则 SHOULD 聚焦跨任务原则，例如 API 登录上下文设置、service 路由打开菜单、绑定前页签校验、前景弹窗优先、非单据模板页面 open-only、从真实 DSL 报告开始诊断
