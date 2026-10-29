## 1. 内容归类

- [x] 1.1 盘点 `AGENTS.md` 现有章节，将内容归类为入口门禁、领域术语、稳定能力语义、人类指南、工程技能配置、一次性历史证据。
- [x] 1.2 确认 `CONTEXT.md`、`docs/adr/`、`docs/agents/` 和 `openspec/specs/` 已覆盖本 change 需要链接的权威来源。
- [x] 1.3 标记需要删除的带日期验证结果、`/tmp` 报告路径、截图路径和页面级或组件级发现。

## 2. 精简入口

- [x] 2.1 将 `AGENTS.md` 改写为固定结构：Scope、Must Follow、Source Of Truth、Core Workflow、Runtime Ground Rules、Verification Gates、Useful Commands、Agent Skills。
- [x] 2.2 保留跨任务运行时 ground rules 和交付门禁，删除或改为链接引用页面级、组件级和一次性历史细节。
- [x] 2.3 确保 `AGENTS.md` 目标长度为 150-250 行，且不超过 300 行硬上限。

## 3. 最小补充文档

- [x] 3.1 如果清理时发现少数高价值内容没有权威归宿，只补充到最合适的现有文档或规格。
- [x] 3.2 不创建新的通用知识库、自动索引或全量迁移文档。

## 4. 验证

- [x] 4.1 运行 `wc -l AGENTS.md`，确认行数不超过 300。
- [x] 4.2 人工检查 `AGENTS.md` 是否包含固定章节，并链接 `CONTEXT.md`、`docs/adr/`、`docs/agents/` 和相关 OpenSpec 规格。
- [x] 4.3 运行 `openspec validate slim-agents-entrypoint --strict`。
- [x] 4.4 运行 `./scripts/check_openspec_language.py --change slim-agents-entrypoint`。
