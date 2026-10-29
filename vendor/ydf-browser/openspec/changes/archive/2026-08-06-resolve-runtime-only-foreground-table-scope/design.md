## Context

共享表格作用域解析当前先从 manifest 筛选表格 region，再把这些 region 交给运行时 DOM 探测。动态模板弹窗可能先渲染子表格 DOM，而当前 manifest 只保留背景主表，因此精确 fieldid 在候选构建前丢失。`ai-observe-7` 的失败报告和 DOM 摘要分别证明了“候选仅含背景表”和“前景子表已存在”。

## Goals / Non-Goals

**Goals:**

- 在共享解析入口支持 manifest 未声明的精确 runtime fieldid。
- 继续复用现有运行时前景、交互性、必需列和执行令牌校验。
- 保持现有失败分类和无副作用失败边界。

**Non-Goals:**

- 不从弹窗标题、表头或模糊文本推断表格 fieldid。
- 不修改动态模板 manifest 生成链路或 DSL schema。
- 不处理 `ai-observe-7` 中独立的工具栏动作缺失问题。

## Decisions

1. 仅在现有 manifest 身份和语义候选均未命中时，把 `target.table` 作为一个临时表格 region 做第二次运行时探测。这样不会扩大已声明表格的匹配面，也不会改变背景拒绝和歧义语义。
2. 临时 region 仍经过现有候选过滤、前景检查、必需列检查和执行令牌生成，不增加页面专用分支或另一套 DOM 查找实现。
3. 回归测试使用 `ai-observe-7` 中的真实 fieldid 形态，但只验证共享解析契约；真实 DSL 负责证明浏览器运行时链路。

## Risks / Trade-offs

- [业务名称可能被当作 fieldid 多探测一次] → 探测失败后保持原有未找到结果，不做文本猜测，也不产生页面副作用。
- [动态 DOM 在探测后立即失效] → 继续使用现有执行令牌校验和最多一次受控重解析。
