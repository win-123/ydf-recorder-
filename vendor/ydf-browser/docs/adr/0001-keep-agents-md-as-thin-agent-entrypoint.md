# 将 AGENTS.md 保持为精简的 agent 入口

`AGENTS.md` 最初承担了保存 agent 流程 notes 和项目结论的职责，但当前仓库已经有了更明确的知识归宿：`CONTEXT.md` 负责领域语言，`openspec/` 负责能力规格和变更历史，`docs/` 负责面向人类的指南，`docs/agents/` 负责 Matt Pocock skills 配置。我们决定将 `AGENTS.md` 保持为新 agent 的精简入口，只保留项目定位、不可违反的执行门禁，以及指向权威文档的链接，不再把它作为长期历史知识库。

`AGENTS.md` 的目标长度是 150-250 行，300 行是硬上限。如果某段内容会让文件超过这个上限，它就应该进入更具体的权威来源，并由 `AGENTS.md` 链接过去，而不是复制到 `AGENTS.md` 正文中。

只有当新 agent 不读某条内容就很可能把任务做错时，这条内容才应该留在 `AGENTS.md`。领域术语属于 `CONTEXT.md`；稳定的能力语义和验收规则属于 `openspec/specs/`；面向用户和维护者的指南属于 `docs/`；Matt Pocock skills 配置属于 `docs/agents/`；一次性报告路径、过期环境观察和带日期的“最近一次验证”说明应删除，或替换为指向权威样例、报告、文档或规格的链接。

精简后的 `AGENTS.md` 应采用稳定结构：Scope、Must Follow、Source Of Truth、Core Workflow、Runtime Ground Rules、Verification Gates、Useful Commands、Agent Skills。这个结构有意只作为索引和门禁清单，不替代被链接的文档。

具体页面和组件发现不应复制进精简后的 `AGENTS.md`。`AGENTS.md` 只允许保留跨任务的运行时 ground rules，例如 API 登录上下文设置、service 路由打开菜单、绑定前先校验页签、运行时 DOM 和前景弹窗优先、非单据模板页面只支持 open-only，以及从真实 DSL 运行报告开始诊断。

瘦身 `AGENTS.md` 不是一次全量迁移工程。如果某个主题已经有权威归宿，就链接到那个归宿，不要复制或重写；只有少数高价值且仍缺少归宿的主题才需要新建文档。带日期的一次性证据和过期观察应删除，而不是迁移。

实际改写应通过一个窄范围 OpenSpec change 承载，名称为 `slim-agents-entrypoint`，让清理工作有明确验收标准，而不是变成主观编辑。这个 change 应验证 `AGENTS.md` 低于硬行数上限、遵循稳定结构、链接到权威来源，并且不重复页面级或组件级细节。

历史运行结果不应保留在 `AGENTS.md` 中。这个文件应保留命令模板和验证原则；具体的旧测试数量、`/tmp` 报告、报告目录 ID、截图，以及带日期的“最近一次验证”声明，应放在 release notes、reports、issues、changes 中，或在不再有用时删除。
