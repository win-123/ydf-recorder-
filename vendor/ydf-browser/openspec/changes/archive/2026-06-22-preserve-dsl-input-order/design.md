## Context

`--dsl` 参数当前由 argparse 保留输入顺序，`_dsl_inputs()` 也按顺序拍平成列表。顺序被打乱发生在 `discover_dsl_files()`：它完成展开和去重后，对所有结果按路径字符串做全局排序。

这个行为对目录输入是合理的，但对显式多文件输入不合理。用户写 `--dsl b.yaml a.yaml` 时，期望执行顺序就是 `b.yaml` 再 `a.yaml`，而不是路径字典序。

## Goals / Non-Goals

**Goals:**
- 显式文件参数按命令行出现顺序进入 `run` 和 `validate`。
- 重复文件去重后保留首次出现的位置。
- 目录和通配符展开出的内部文件列表保持稳定排序。

**Non-Goals:**
- 不改变 `--dsl` 参数语法。
- 不改变 case 在单个 suite 内的执行顺序。
- 不承诺 `--concurrency > 1` 时的完成顺序。

## Decisions

1. 保留发现阶段的插入顺序，不再对最终结果做全局排序。

   Python 字典已经保留插入顺序，现有 `deduped` 结构足够表达“首次出现 wins”。最小实现是返回 `list(deduped.values())`。

   备选方案是在每个路径上记录序号再排序，但这只是绕回插入顺序，代码更多。

2. 继续让目录和通配符各自排序。

   用户传目录或 glob 时，shell/文件系统顺序本身不应泄漏到运行结果。保持 `_discover_existing_path()` 内部排序，以及 `glob.glob()` 结果的稳定化，可以让批量展开可复现。

3. `run` 和 `validate` 共用同一个发现函数。

   两个命令已经共用 `discover_dsl_files()`，修这一处即可避免验证通过顺序和运行顺序分叉。

## Risks / Trade-offs

- [Risk] 依赖旧全局路径排序的批量命令会看到执行顺序变化。→ Mitigation: 这是对显式命令行顺序的修正；需要路径排序时，用户仍可按期望顺序传参或传目录。
- [Risk] `--concurrency > 1` 容易被误解为完成顺序也稳定。→ Mitigation: 规格只承诺执行计划和调度输入顺序，不承诺并发完成顺序。
