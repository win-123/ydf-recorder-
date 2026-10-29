## Context

当前 CLI 在 `ydf_browser/cli.py` 的 `build_parser()` 中直接使用 Python 标准库 `argparse` 注册命令和参数，但大部分 `add_parser()` 与 `add_argument()` 没有 `help` 或 `description`。因此 argparse 只能输出参数名和自动生成的 metavar，无法表达 DSL 输入、浏览器 profile、并发、AI 观察、请求转发和报告路径等领域约束。

README 和发布测试人员指南已经包含较完整的操作示例，但它们不是命令行现场可查询的参数参考，也不适合替代 `--help` 的短说明。详见 proposal.md 和 `specs/cli-help-descriptions/spec.md`。

## Goals / Non-Goals

**Goals:**

- 复用现有 argparse parser，为所有命令和参数提供准确、简洁的中文帮助文本。
- 让 `run --help` 可以直接解释主要输入模式、默认值、组合限制和产物位置。
- 用 argparse 的标准帮助格式组织较多的 `run` 参数，减少平铺输出的阅读成本。
- 保持帮助可离线运行，并通过 CLI 回归测试锁定关键说明。
- 让 README 和发布测试人员指南指向 CLI 帮助，避免复制完整参数矩阵。

**Non-Goals:**

- 不引入 Click、Typer、Rich 或其它 CLI 框架。
- 不改变任何参数名称、解析类型、默认执行语义、退出码、报告结构或运行时行为。
- 不把 `profile clear --cookies/--cache/--storage` 扩展为局部清理能力，也不在本 change 中重新设计 profile 管理。
- 不将 README 改写成逐参数手册；详细参数语义以命令行帮助和 OpenSpec 规格为准。

## Decisions

### 1. 在现有 argparse 定义上补齐说明

选择直接为已有 parser 和 argument 增加 `description`、`help`、必要的 `metavar`，不新增命令抽象或外部依赖。这样改动集中在现有 CLI 入口，保留 argparse 的参数解析、错误处理和 `--help` 退出行为。

备选方案是引入 Click/Typer 或单独维护一份帮助文档。前者会扩大依赖和迁移风险，后者容易与实际参数漂移，均不符合本次只解决帮助说明缺失的范围。

### 2. 对 `run` 使用标准参数分组

将 `run` 参数按输入与 fixture、环境与浏览器、用例筛选、执行策略、性能与 AI 观察、网络转发、报告输出分组。分组只影响帮助呈现，不改变 argparse 的参数解析；每组中的说明保持一到两句，优先说明用户决策所需的格式和约束。

对 `--dsl`、`--dsl-list`、`--var`、`--forward` 等容易误用的参数使用明确的 metavar，例如文件/目录/通配符、清单文件、`KEY=VALUE`、`PATH/**=TARGET`，避免输出退化为 Python dest 名称。

### 3. 使用标准默认值展示，避免重复维护

对具有稳定默认值的 parser 使用 argparse 标准的默认值帮助格式，让 `ydf`、并发 `1`、报告目录 `reports` 等信息自动显示；对默认值为 `None` 或受 DSL/环境决定的参数，在手写说明中解释“未指定时”的行为，不输出无意义的 `None`。

### 4. 保持不支持参数的行为边界

`profile clear` 当前的局部清理选项会进入参数解析，但随后由执行逻辑拒绝。为避免本 change 偷改 CLI 行为，先保留现有解析和拒绝路径，并在帮助中明确“当前不支持局部清理”；是否移除这些兼容参数另开行为变更处理。

### 5. 采用代表性断言而不是完整输出快照

测试直接从 parser 生成 root、`run`、`validate`、`profile clear` 等帮助文本，断言命令描述、关键参数说明、默认值/约束和不支持参数提示存在。避免锁定完整 whitespace 或 argparse 排版，降低 Python 版本和说明微调带来的无价值失败。

### 6. 文档只补入口，不复制帮助矩阵

README 和 `docs/release/tester-guide.md` 增加“查看命令帮助”的短入口，并保留现有高层示例。这样命令行帮助负责即时参数语义，用户指南负责安装、配置和典型工作流，两者职责清晰。

## Risks / Trade-offs

- [Risk] `run --help` 参数较多，补充说明后输出仍可能较长。→ [Mitigation] 使用语义分组、短句和明确 metavar；不把完整 DSL 手册塞进 help。
- [Risk] 帮助文本可能随着运行约束变化而过时。→ [Mitigation] 将关键约束写入规格，并在 CLI 测试中覆盖代表性说明；涉及行为变更时同步更新 help。
- [Risk] `profile clear` 的局部清理参数容易让用户误以为可用。→ [Mitigation] 明确标记当前拒绝行为，并将真正的局部清理另作为独立变更。
- [Risk] 不同 Python 版本的 argparse 排版存在差异。→ [Mitigation] 测试语义片段，不做完整输出快照。

## Migration Plan

无需数据或配置迁移。实现后使用当前源码入口验证所有 `--help` 命令，再运行聚焦 CLI 测试和完整测试集；帮助文本发布后，旧命令仍按原有参数和运行语义执行。

回滚时只需回滚帮助文本、分组和相关文档/测试改动，不涉及运行数据、浏览器 profile 或远程环境。

## Open Questions

无。参数范围、行为兼容边界和 `profile clear` 的后续处理边界已在 proposal、spec 和本设计中确定。
