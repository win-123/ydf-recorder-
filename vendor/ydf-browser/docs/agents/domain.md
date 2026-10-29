# 领域文档

工程技能在探索本仓库时，按 single-context 布局读取领域文档。

## 读取规则

开始分析前，优先读取：

- `CONTEXT.md`：`ydf-browser` 的领域上下文和术语。
- `docs/adr/`：与当前改动相关的架构决策记录。

如果这些文件暂时不存在，继续执行即可，不要因为缺失而阻塞任务。后续可由 `/domain-modeling`、`/grill-with-docs` 或 `/improve-codebase-architecture` 在真正沉淀术语和决策时再创建。

## 目录布局

```text
/
├── CONTEXT.md
└── docs/
    └── adr/
```

## 使用约定

输出 Issue、诊断假设、重构计划、测试名称或交付说明时，优先使用 `CONTEXT.md` 中定义的术语。

如果需要使用的概念尚未出现在 `CONTEXT.md` 中，先判断是不是自己发明了项目里不用的说法；如果确实是领域缺口，再在合适时机补充领域文档。

如果建议或实现与已有 ADR 冲突，必须明确指出冲突点，不要静默覆盖历史决策。
