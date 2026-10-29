## Context

`--dsl-list` 当前在 CLI 输入展开层被还原为普通 `--dsl` 文件列表，随后进入全局 runner。该实现保留了清单行顺序，却也继承了 `--concurrency > 1` 的并发调度，因此后续 DSL 可能在前序 DSL 完成前启动。清单的真实用途是表达有前后依赖的用例链，执行计划有序不足以保证依赖成立。

## Goals / Non-Goals

**Goals:**

- 让包含 `--dsl-list` 的一次 `run` 严格按展开后的 suite 和 case 顺序逐个完成。
- 对与严格顺序矛盾的显式并发参数快速失败，并给出可执行的修正提示。
- 保持普通 `--dsl` 批量运行的既有并发语义。

**Non-Goals:**

- 不设计依赖图、阶段并发或清单专属 DSL。
- 不改变 `validate --dsl-list`，因为校验命令不执行业务用例。
- 不修改 runner 的通用调度算法或报告结构。

## Decisions

### Decision: 在 CLI 入口拒绝矛盾的参数组合

`_cmd_run()` 在加载 DSL 前检查输入来源；只要存在 `--dsl-list` 且 `concurrency > 1`，就抛出说明清单仅支持串行执行的参数错误。`concurrency == 1` 继续复用 runner 已有串行路径，自然保证前一个 case 完成后才启动下一个 case。

选择入口校验而不是在 runner 中强制改写并发值，是因为只有 CLI 输入层保留 `dsl_list` 来源信息。静默把并发值降为 1 会让报告和用户预期不一致；为 runner 增加清单概念则会扩大通用调度接口的职责。

### Decision: 混合输入整体采用清单的严格语义

命令中同时出现 `--dsl` 和 `--dsl-list` 时，同样拒绝 `concurrency > 1`。不引入“清单片段串行、普通 DSL 片段并行”的阶段模型，因为它难以从现有参数顺序直观推断，也不是依赖链需求所需。

### Decision: 清单顺序覆盖所有展开后的 case

允许的 `concurrency == 1` 通过现有串行 helper 按 suite 顺序和 suite 内 case 顺序执行。无需新增文件级屏障；全局串行是表达前后依赖最小且无歧义的语义。

## Risks / Trade-offs

- [Risk] 现有用户可能已用 `--dsl-list --concurrency N` 跑相互独立的用例。→ Mitigation: 明确报错并提示改用多个 `--dsl`、目录或通配符输入来保留并发。
- [Risk] 参数同时触发持久化 profile 和清单并发限制时，错误来源可能不清楚。→ Mitigation: 优先报告更直接的 `--dsl-list` 顺序冲突；两种修正方式都要求将并发设为 1。
- [Risk] 全局串行牺牲同一清单内可安全并发的局部用例。→ Mitigation: 本能力以依赖链为事实语义；需要并发的集合不使用 `--dsl-list`。
