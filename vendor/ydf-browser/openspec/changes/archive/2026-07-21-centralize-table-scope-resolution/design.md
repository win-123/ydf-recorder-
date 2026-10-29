## Context

`WorkflowExecutor` 当前分别为主表、可编辑表格、行级动作、列断言和链接点击推导 `table`、`table_fieldid` 与列集合，`PlaywrightRuntime` 又为各动作重新选择 DOM 根。调用者通过多个字符串参数和运行时 `last_*` 状态拼接诊断，导致表格身份规则跨 seam 泄漏。近期关于列归属、前景 fieldid、嵌套 WUI 表格和可编辑表格语义标题的修复都落在这条重复链路上。

本次设计沿用 `CONTEXT.md` 中“表格作用域”的领域名称。它是单据页表格类 DSL 动作唯一指向的表格范围，不包含行匹配和动作执行。

## Goals / Non-Goals

**Goals:**

- 建立一个 deep module，集中 DSL 目标、manifest 身份、运行时前景证据、必需列和诊断的解析规则。
- 让调用者和测试通过同一 interface 消费表格作用域，提高 locality 与 leverage。
- 保持现有 DSL 字段，明确收紧 fieldid、歧义、前景和缺列行为。
- 将成功和失败证据绑定到同一次解析，避免依赖动作后的页面重扫。

**Non-Goals:**

- 不拆分 `WorkflowExecutor` 或 `PlaywrightRuntime` 的其它职责。
- 不把弹出参照内部候选表格纳入单据页表格作用域。
- 不接管行匹配、树形展开、checkbox 选择、单元格录入或点击动作。
- 不新增策略类、factory 或第三方依赖。
- 不新增 DSL 字段；显式 fieldid 继续通过 `target.table` 精确匹配 region fieldid 或 runtime fieldid 表达。

## Decisions

### Decision: 新增单一 `table_scope.py` module

新增 `ydf_browser/table_scope.py`，集中不可变的作用域请求、候选证据、解析结果和解析错误。公开 interface 接收 manifest、目标表格文本、动作必需列、允许的表格类型以及一个运行时证据 adapter，返回稳定的表格身份和证据；不返回 Playwright `Locator` 或 CSS selector。

选择单一 module 而不是按行选择、断言、行级动作和可编辑表格分别抽取，是因为这些动作共享同一身份与歧义规则。按动作拆分只会制造 shallow module，删除后复杂度不会集中。

### Decision: runtime adapter 只提供候选事实，不决定业务消歧

runtime adapter 负责为 manifest 候选报告当前前景、存在、可见、可交互、实际 fieldid 和可见列。`table_scope.py` 负责统一应用 hard fieldid、必需列和唯一候选规则。这样真实 Playwright 与测试 adapter 是两个真实 adapter，但消歧规则只有一份。

不让 runtime 动作继续接收散落的 `table`、`table_fieldid`、`table_columns` 并自行兜底。动作逐步改为接收解析结果；过渡期兼容调用仅允许把解析结果展开到现有参数，不得改变目标。

### Decision: fieldid 精确匹配优先且不可回退

`target.table` 与 region fieldid 或 runtime fieldid 精确相等时，候选立即进入 hard scope。运行时不可交互或缺少必需列时直接失败。语义名称只在没有精确 fieldid 匹配时参与候选解析。

该选择牺牲旧 DSL 的宽松兜底，但能避免在多表格单据页上静默操作错误数据。

### Decision: 必需列由动作声明，否定列除外

executor 为每种动作提取必需列：行匹配列、断言目标列、行值字段列、链接列、可编辑表格字段列。`table.assert_columns.target.absent` 不属于必需列，因为它表达列应不存在。module 只验证列归属，不解释行条件和值。

### Decision: 每步新解析，执行前最多受控重试一次

解析结果不跨 DSL 步骤缓存。runtime adapter 为解析结果保留不暴露 Playwright 细节的执行令牌；动作执行前由同一 adapter 校验令牌。令牌失效且尚无页面副作用时，resolver 最多重建一次结果，第二次失败即停止。

不在动作内部静默按表名重扫，避免形成第二套 interface。

### Decision: 证据属于解析结果

解析结果始终包含紧凑身份、已校验列和候选摘要。成功报告只输出紧凑字段；解析错误携带全部候选、排除原因和 manifest 差异。executor 直接把这份证据写入步骤数据或失败报告，不再从多个 `last_*` 字段拼装表格作用域诊断。

## Risks / Trade-offs

- [Risk] 全量迁移表格动作会扩大一次改动范围 → 按 tracer slice 迁移：先建立 module 与行选择，再迁移断言、行级动作、链接和可编辑表格；每片保持聚焦测试通过。
- [Risk] 现有 FakeRuntime 没有运行时证据 adapter → 提供最小测试 adapter，并逐步删除依赖 private helper 的测试，不建立通用 mock framework。
- [Risk] 真实 DOM 的前景与列采集可能有短暂不稳定 → 单次解析采集一致快照，执行前令牌失效仅允许一次无副作用重试。
- [Risk] 旧 DSL 依赖宽松兜底而失败 → 错误报告列出候选、fieldid、前景状态和必需列，指导用户补充明确表格身份。
- [Trade-off] 首期不统一弹出参照表格 → 保持范围可控；只有未来证明两处身份规则真实共享时才扩展 module。

## Migration Plan

1. 以 TDD 建立 `table_scope.py` 的纯解析规则和测试 adapter。
2. 迁移 `table_row_selection.select`，验证 hard fieldid、多候选、前景和复合列预校验。
3. 迁移表格断言、行级动作与单元格链接，删除对应重复解析 helper。
4. 迁移可编辑表格新增行与录入，保留既有弹出参照和单元格激活实现。
5. 更新报告字段、领域词汇和用户文档，运行真实 DSL 验证与完整回归。

若迁移期间出现无法保持既有真实用例的非预期行为，可按动作回退到迁移前提交；不得保留同时生效的两套表格消歧规则。

## Open Questions

无。职责、硬 fieldid、歧义、前景、列预校验、运行时事实源、刷新、诊断、首期范围和测试迁移已在实施前确认。
