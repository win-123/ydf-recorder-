## Context

当前顶层 parser 使用必需的 subparser。用户直接执行 `ydf-browser` 时，argparse 在进入 `main()` 的命令分发前就返回“缺少 command”错误；而 `ydf-browser --help` 已经能够生成完整且有描述的顶层帮助。详见 proposal.md 和 `specs/no-args-help/spec.md`。

## Goals / Non-Goals

**Goals:**

- 让完全无参数的调用复用现有顶层 parser 帮助并以 0 退出。
- 保持无参数路径不触发登录、配置、浏览器和网络逻辑。
- 保持所有带参数的解析错误和已有命令行为不变。
- 用一个最小的 CLI 测试固定 stdout、退出码和无副作用语义。

**Non-Goals:**

- 不为无参数调用新增默认业务命令或自动运行 DSL。
- 不改变 `--help`、`--version` 或嵌套命令帮助的内容。
- 不改变未知参数、缺失值或未知命令的退出码。
- 不引入新的 CLI 框架或帮助文本副本。

## Decisions

### 1. 让顶层 subparser 非必需并显式处理空命令

将顶层 subparser 的 `required` 改为 `False`，解析后若 `args.command is None`，直接调用同一个 parser 的 `print_help()` 并返回 0。这样无参数调用和显式 `--help` 共用同一份 argparse 帮助定义，不需要复制命令列表或文案。

嵌套的 `menu`、`template`、`page` 和 `profile` subparser 继续保持必需；它们仍会对 `ydf-browser menu` 等不完整调用报告参数错误。只有顶层完全无参数调用进入帮助分支。

### 2. 在命令分发前处理空命令

空命令分支放在 `parse_args()` 和 `_explicit_options` 初始化之后、现有命令分发之前。`--version` 和 `--help` 仍由 argparse action 直接处理；任何显式参数解析错误仍在进入该分支前失败。

### 3. 使用 stdout 和退出码 0

无参数调用被视为人类探索入口，而不是失败的业务执行。帮助写入 stdout 并返回 0，便于终端、脚本和 AI agent 直接读取。未知命令等显式错误仍保留 argparse 的 stderr 和非零退出码。

### 4. 文档只补行为提示

README 和测试人员指南在已有 `--help` 入口附近增加一句：直接执行 `ydf-browser` 也会显示顶层帮助。无需复制帮助文本或增加独立命令手册。

## Risks / Trade-offs

- [Risk] 某些脚本可能把无参数调用的退出码 2 当作配置错误。→ [Mitigation] 该调用本身没有业务动作，改为成功帮助入口；显式参数错误仍保持非零，且变更范围清晰。
- [Risk] 无参数帮助与显式帮助未来可能因 parser 分支变化而不一致。→ [Mitigation] 两者复用同一个 parser，并增加输出一致性测试。
- [Risk] 顶层 parser 的 `required` 改动可能意外放宽不完整命令。→ [Mitigation] 仅在 `args.command is None` 分支返回帮助，嵌套 subparser 继续使用 `required=True`，并覆盖未知/不完整命令测试。

## Migration Plan

无需数据、配置或依赖迁移。实现后运行无参数、显式 `--help`、未知命令和完整测试集；回滚时恢复顶层 subparser 的必需行为及对应测试/文档即可。

## Open Questions

无。
