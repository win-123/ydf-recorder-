## Context

参见 [proposal.md](./proposal.md) 的 `Why`。当前 `WorkflowExecutor._handle_open_menu` 及相邻私有方法负责菜单解析、页面触发、页面实际响应消费、manifest 构建、首次展示工作面等待、绑定、承载识别、计时和报告组装；`PlaywrightRuntime` 同时保存服务详情、模板和模板业务错误 payload，并拥有工作面扫描、页面错误游标和承载识别。两者以多个可选方法和可变字段形成宽 interface，测试分别穿过 executor 与 runtime 私有 implementation。

现有规格已经稳定规定菜单页面实际模板响应、全部首次展示工作面终态、100ms 轮询、500ms 稳定快照、120 秒共享步骤期限、open-only、菜单承载方式、profile page 交接和计时字段。本 change 只移动这些既有语义。

## Goals / Non-Goals

**Goals:**

- 建立 `ydf_browser.menu_opening` deep module，以一个公开有副作用操作隐藏完整菜单打开流程。
- 让菜单打开期间的 payload、工作面历史、期限、取消检查和计时具有单一 locality。
- 让生产与 fixture adapters 穿过真实 internal seams，删除假想 runtime 的反射式兼容。
- 让 tests 通过 module interface 验证既有规格场景，并删除跨过 interface 的私有实现测试。
- 保持失败页面可检查，并保持现有 DSL、报告、contract path 和计时语义。

**Non-Goals:**

- 不改变登录、租户、默认组织、业务年度、持久化 profile 或用例级 page 生命周期。
- 不合并通用 `ActionCompletion`，不处理菜单打开后的动态模板恢复。
- 不改变 `YondifGateway.fetch_template` 的独立命令用途。
- 不新增通用 DOM adapter、插件机制、新依赖、双轨开关或用户可见能力。
- 不拆分多个源文件；只有实施证明出现第二个真实 internal seam 时才重新评估。

## Decisions

### 1. 一个公开操作承载完整菜单打开

新增 `MenuOpening.open(request) -> MenuOpeningResult`。请求只包含菜单路径、共享绝对期限、取消检查和是否采集性能字段；构造时注入菜单解析与浏览器 runtime adapters。结果使用 frozen dataclass，承载后续步骤需要的 `MenuTarget`、`PageManifest`、`BindingResult`、页面状态，以及现有步骤报告需要的模板、承载、工作面和计时事实。

替代方案是公开 resolve、navigate、template、wait 和 bind 等阶段方法。该方案要求 caller 理解调用顺序、payload 生命周期和失败组合，interface 几乎等于 implementation，因此拒绝。

### 2. 一个结构化失败类型保存最后证据

`MenuOpeningError` 保存现有错误文本和 `data`，executor 将其映射为既有失败报告；为保持报告兼容，失败数据中的错误类型继续映射为 `OpenMenuCompletionError`。失败前清空旧 executor 页面上下文，失败后不关闭或回滚当前浏览器页面，使失败证据包和失败现场暂停继续工作。

普通菜单解析异常继续保留原异常文本；module 只在需要附带菜单完成证据时包装为结构化失败。

### 3. module 独占语义，adapters 只执行外部交互

菜单专属的服务详情响应识别、模板响应消费、manifest 构建、工作面规格、运行时扫描解释、终态状态机、承载结果、绑定、错误组合和计时都属于 module implementation。

生产 runtime adapter 继续负责浏览器 context、profile page 交接、cookies、实际导航、页面求值、等待和事件捕获；菜单解析 adapter 继续通过 `YondifGateway.resolve_menu` 读取菜单树。fixture adapters 提供内存模板、运行时元素、页面状态和确定性等待。internal seams 不从 module 导出。

不建立覆盖 Playwright 全部操作的通用 adapter；生产 implementation 复用当前 page/runtime 能力，测试使用现有 fixture 与本地 stand-in。

### 4. 生产模板只来自菜单页面实际响应

生产路径在解析出 `serviceCode` 后直接触发菜单路由，随后消费页面捕获的服务详情、有效模板或模板业务错误。技术错误可被页面后续成功响应恢复；未明确认定为非单据模板页面时不得调用 `gateway.fetch_template` 兜底。

fixture adapter 直接提供内存模板，保持 fixture CLI 行为。`YondifGateway.fetch_template` 保留给 `template fetch`、分析等独立命令，不进入生产菜单打开流程。

### 5. 菜单打开拥有独立完成政策

菜单解析、浏览器打开、页签校验、页面模板等待、manifest 构建、全部首次展示工作面终态和绑定共享请求期限。工作面每 100ms 检查，优先状态转换，缺少转换时使用全页面共享 500ms 稳定快照。该政策不复用 `ActionCompletion`，因为通用点击动作的兼容上限和完成信号不同。

取消在每次外部调用和轮询前检查。超时与业务错误返回最后工作面、页面错误、通知和模板错误证据。

### 6. executor 与 runtime 测试收窄到各自 interface

新增 `tests/test_menu_opening.py`，通过 `MenuOpening.open` 覆盖页面实际模板响应、技术错误恢复、open-only、动态工作面、状态转换、稳定快照、业务错误、超时、承载识别、绑定和计时。测试只断言公开结果或结构化失败。

`tests/test_runtime.py` 只保留 profile page 交接、cookies、导航、页面响应捕获及 Playwright 求值 adapter 行为；`tests/test_executor.py` 只保留 DSL 分派、当前状态接收、步骤报告映射和失败映射。被 interface tests 替代的私有 orchestration tests 删除，不叠加保留。

### 7. 移动后删除，不保留双轨

先以一个 interface test 建立 RED，再实现最小 module 和 fixture 路径；随后逐个迁移生产响应、工作面终态、绑定和计时，每个 vertical slice 通过后删除原 implementation。最终 executor 不再拥有菜单打开私有轮询，runtime 不再暴露菜单专属可变 payload。

不增加 feature flag。回退方式是整体回退本次纯代码结构变更，无数据迁移和发布切换。

## Risks / Trade-offs

- [移动期间遗漏 executor 与 runtime 的隐式状态] → 先盘点读写点，每个 vertical slice 使用 interface characterization test 固定结果和失败数据。
- [工作面扫描移动造成真实页面时序回归] → 保留原脚本和轮询常量，运行两条现有真实 DSL，并检查完成信号与计时。
- [fixture 与生产来源差异掩盖页面响应缺陷] → interface tests 分别使用 fixture template adapter 和页面响应 adapter，不让生产路径调用模板预取。
- [失败类型重命名改变报告] → executor 显式保留既有 `OpenMenuCompletionError` 报告类型、文本和 `data`。
- [单文件再次变浅] → 以 interface depth 而非文件行数判断；只有出现第二个真实 adapter 或独立变化轴时才拆分。
- [真实环境数据漂移] → 使用只打开或查询的既有真实 DSL；先分类环境与数据问题，失败时不得声称完成。

## Migration Plan

1. 建立 `MenuOpeningRequest`、`MenuOpeningResult`、`MenuOpeningError` 和公开 interface 的首个失败测试。
2. 实现 fixture 菜单解析、内存模板、manifest、绑定和结果映射，切换 fixture executor 路径。
3. 迁移生产页面响应消费、工作面扫描与终态状态机，删除 executor 对应私有方法。
4. 迁移菜单承载、页面状态、计时和失败证据，删除 runtime 菜单专属 side channel。
5. 收窄 runtime/executor tests，确认 package 外不调用 menu module 内部函数。
6. 运行聚焦、全量、OpenSpec、语言和 diff 门禁，再执行两条真实 DSL。
7. 任一步骤出现无法保持既有语义的情况时停止迁移并整体回退当前 change；用户可见规格缺口另开 change。
