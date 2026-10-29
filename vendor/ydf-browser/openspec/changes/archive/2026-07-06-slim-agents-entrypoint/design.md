## Context

当前仓库已经有分层知识归宿：

```text
AGENTS.md        -> 新 agent 入口、硬门禁、链接索引
CONTEXT.md       -> 领域语言和术语
openspec/specs/  -> 稳定能力语义和验收规则
docs/            -> 面向人类的指南和 ADR
docs/agents/     -> Matt Pocock skills 配置
```

`AGENTS.md` 现在承担了所有层的职责，导致新 agent 读取成本高，也容易把旧 `/tmp` 报告、最近一次验证结果、页面级发现误当成当前事实。ADR 已经给出方向：入口要薄，权威事实要回到对应文档。

## Goals / Non-Goals

Goals:

- 将 `AGENTS.md` 收敛为新 agent 的精简入口。
- 保留会直接影响任务成败的跨任务门禁和运行时 ground rules。
- 用链接指向权威来源，减少重复和过期历史。
- 让后续维护可以用行数、章节结构和内容边界检查结果。

Non-Goals:

- 不重写全部历史知识为新文档。
- 不新增通用知识库、索引生成器或自动同步机制。
- 不改变 OpenSpec 语言门禁、DSL 行为或 ydf-browser 运行时代码。

## Decisions

`AGENTS.md` SHALL 使用以下稳定结构：

```text
Scope
Must Follow
Source Of Truth
Core Workflow
Runtime Ground Rules
Verification Gates
Useful Commands
Agent Skills
```

保留规则按“新 agent 不读就很可能做错”判断。跨任务的运行时规则可以留在 `Runtime Ground Rules`，例如 API 登录上下文、菜单 service 路由、绑定前页签校验、前景弹窗优先、非单据模板页面 open-only、从真实 DSL 报告开始诊断。

页面级和组件级发现不留在入口正文。稳定语义进入对应 `openspec/specs/`，领域术语进入 `CONTEXT.md`，工程技能配置进入 `docs/agents/`，一次性报告路径和带日期观察删除或仅通过更权威的报告、issue、change 链接引用。

## Risks / Trade-offs

- 风险：删除过多细节会让 agent 少看关键约束。缓解：只删除已有权威归宿或明显过期的一次性证据；跨任务门禁保留。
- 风险：把所有内容迁移成新文档会扩大范围。缓解：本 change 不做全量迁移，只补少量确实缺失且仍高价值的权威归宿。
- 取舍：行数硬上限 300 不是为了格式洁癖，而是防止入口重新膨胀成历史知识库。

## Migration Plan

1. 盘点 `AGENTS.md` 内容并按权威归宿分类。
2. 改写 `AGENTS.md` 为固定章节结构，保留门禁、核心流程、运行时 ground rules 和链接。
3. 删除一次性报告、截图、`/tmp` 路径、带日期的最近验证结果和页面级细节。
4. 仅在缺少权威归宿且仍会反复影响 agent 判断时补充最小文档。
5. 验证行数、结构、OpenSpec 结构和语言门禁。
