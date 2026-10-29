## 1. OpenSpec 配置

- [x] 1.1 在 `openspec/config.yaml` 增加项目级中文生成上下文，明确正文使用简体中文、机器标记保留英文。
- [x] 1.2 为 `proposal`、`specs`、`design`、`tasks` 增加 artifact-specific rules，约束各类文档的兼容中文输出边界。

## 2. 验证

- [x] 2.1 运行 `openspec status --change localize-openspec-artifacts`，确认 change 已达到 apply-ready。
- [x] 2.2 运行 `openspec validate localize-openspec-artifacts --strict`，确认规格文档仍可被 OpenSpec 解析。
- [x] 2.3 检查 `openspec instructions` 输出，确认项目级中文规则会注入后续 artifact 生成上下文。
