## Why

当前项目的 OpenSpec 生成链路默认产出英文 proposal、design、specs 和 tasks，不利于政务业务需求沉淀、团队交接和后续 agent 复用。需要在不破坏 OpenSpec CLI 解析规则的前提下，让新生成的文档优先使用简体中文表达。

## What Changes

- 在项目 OpenSpec 配置中增加中文生成约束，要求文档正文、业务说明、设计取舍和任务描述使用简体中文。
- 保留 OpenSpec 解析依赖的英文结构标记，例如 `## Why`、`## What Changes`、`## ADDED Requirements`、`### Requirement:`、`#### Scenario:`、`MUST`、`SHALL`、`WHEN`、`THEN`。
- 为 proposal、specs、design、tasks 分别补充 artifact 级规则，降低后续生成时误把机器可解析标题翻译成中文的风险。

## Capabilities

### New Capabilities
- `openspec-artifact-language`: 约束本项目 OpenSpec artifacts 的语言输出策略，覆盖中文正文和英文机器标记的兼容边界。

### Modified Capabilities
- None

## Impact

- 影响文件：`openspec/config.yaml`
- 影响流程：后续通过 OpenSpec skills/CLI 创建 artifact 时会收到项目级中文生成规则。
- 不改变业务代码、CLI schema、验证器、归档逻辑或既有规格文件内容。
