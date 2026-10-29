## Context

OpenSpec 的 `spec-driven` schema 和 CLI 解析器当前依赖若干英文 Markdown 结构。项目现有 `openspec/config.yaml` 只有 `schema: spec-driven`，没有语言偏好，因此 agent 按内置英文模板生成 proposal、specs、design 和 tasks。

目标不是重写 OpenSpec，也不是把所有标题翻译成中文，而是在项目级配置里向 agent 注入稳定约束：正文用中文，机器可解析标记保留英文。

## Goals / Non-Goals

**Goals:**
- 后续生成的 OpenSpec 文档正文默认使用简体中文，便于政务业务场景阅读和交接。
- 保留 OpenSpec validate、status、archive、apply 所需英文结构标记。
- 将规则落在 `openspec/config.yaml`，让项目内后续 OpenSpec instructions 自动携带这些约束。

**Non-Goals:**
- 不修改 OpenSpec CLI 或内置 package schema。
- 不翻译已经归档或已经存在的主规格文件。
- 不创建项目级 schema override，除非未来发现配置规则不足以稳定约束生成质量。
- 不影响 ydf-browser 运行时代码和测试链路。

## Decisions

1. 使用 `context` 描述项目级语言策略。
   - 理由：`context` 会注入所有 artifact instructions，适合放全局、跨 artifact 的语言约定。
   - 替代方案：复制并覆盖整个 `spec-driven` schema。这个方案控制力更强，但维护成本更高，且容易与 OpenSpec 升级漂移。

2. 使用 `rules` 为 proposal、specs、design、tasks 分别补充具体约束。
   - 理由：不同 artifact 的解析敏感点不同。尤其 specs 需要明确保留 delta headers、Requirement/Scenario 前缀和 MUST/SHALL。
   - 替代方案：只写一条全局 context。这个方案简洁，但对 specs 的防误翻译约束不够强。

3. 保留英文机器标记，不追求全中文标题。
   - 理由：OpenSpec 当前解析器硬编码了 `## Requirements`、`## ADDED Requirements`、`### Requirement:`、`#### Scenario:` 等结构。
   - 替代方案：改 CLI 支持中文结构。这个方案超出当前项目范围，也会引入工具链兼容风险。

## Risks / Trade-offs

- [Risk] agent 仍可能在个别生成中误翻译解析敏感标题。缓解：在 `rules.specs` 中列出禁止翻译的具体标记，并通过 `openspec validate` 及时发现。
- [Risk] `context` 和 `rules` 只能影响通过 OpenSpec instructions 生成的文档，不能约束手写文档。缓解：在项目约定中明确后续手写 artifacts 也遵守同一策略。
- [Risk] 现有主规格仍是英文，短期会出现新旧语言混合。缓解：本次不批量翻译历史文档，避免无业务变更的规格噪音。

## Migration Plan

1. 在 `openspec/config.yaml` 增加项目级 `context`。
2. 为 `proposal`、`specs`、`design`、`tasks` 增加 artifact-specific `rules`。
3. 运行 `openspec status` 和 `openspec validate` 确认当前 change 可解析。
4. 后续新建 change 时观察生成效果，必要时再考虑项目级 schema override。

## Open Questions

- 是否需要未来单独把既有主规格文件翻译成“兼容中文”格式？当前不建议在本次变更中处理。
