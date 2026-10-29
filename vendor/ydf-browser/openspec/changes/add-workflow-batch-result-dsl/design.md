## Context

当前组件 DSL 由 `ydf_browser/dsl.py` 的 `COMPONENT_TARGET_SCHEMAS` 做结构校验，再由 `ydf_browser/executor.py` 按组件和操作分派到运行时。点击类动作已经有统一的页面提示捕获、步骤超时、前景控件定位和未处理错误保护；`notification.assert` 也已经通过业务断言回执写入结构化观察结果。新增能力应复用这些边界，而不是为采购计划页面增加专用流程。

YonDiF 的非 `iuap` 批量工作流结果层是工作流模块共享的自定义浮层：外层提供批量统计及“确认”“查看详情”入口，点击“查看详情”后才出现标准详情弹窗。它可能使用 `.error-content` 等实现类名，但这些类名本身不能证明业务语义。工具只能修改 `ydf-browser`，因此识别、操作和证据采集必须建立在运行时可见 DOM、作用域和交互状态之上。

## Goals / Non-Goals

**Goals:**

- 在现有组件 DSL、schema 校验、executor/runtime 分层中增加 `workflow_result.assert|details|confirm`。
- 以结果层根作用域为边界，组合可见工作流语义、批量统计和操作入口完成稳定识别。
- 让统计断言、详情采集和外层关闭进入 `data.workflow_result`，并继续使用现有业务断言回执、错误分类和诊断证据。
- 在点击类动作之后保护未声明结果层；明确要求先断言，再查看详情或关闭外层。
- 保持全部成功时 `notification.assert` 的现有路径，并使能力在 doctor 中可发现、仅在本次实际使用时进入 enabled。

**Non-Goals:**

- 不把任意自定义浮层抽象成通用 overlay DSL，也不为某个采购计划菜单添加页面专用分支。
- 不修改 `ams-pvdf` 前端或要求前端增加稳定选择器。
- 第一版不提供失败详情行级 DSL 断言、不替代既有 `dialog.confirm`，也不伪造全部成功结果层。
- 不增加固定 sleep、页面专用等待字段或额外运行开关。

## Decisions

### 1. 使用独立组件并在解析阶段约束 target

在 `COMPONENT_TARGET_SCHEMAS` 中登记三个操作，并在 `_validate_component_target` 中增加专用校验：`assert` 的 `target` 至少包含一个 `total`、`succeeded`、`failed` 整数字段；多个统计字段全部精确匹配；可选标题/提示文案只作为辅助条件。`details` 和 `confirm` 只接受可选的入口标签（缺省分别使用“查看详情”和“确认”），不接受 selector、坐标或页面内部 class。

这样可以在浏览器启动前拒绝空断言和字符串统计，保持 DSL 语义与现有组件 schema 一致。考虑过把统计放进 `notification.assert` 或让 `toolbar.click` 自动完成断言，但前者无法表达外层/内层层次，后者会隐藏业务断言并破坏现有失败保护，因此不采用。

### 2. 在 runtime 建立结果层快照，而不是让 executor 解析裸 DOM

runtime 增加一个面向语义的结果层观察/操作边界，返回统一快照（结果层根、可见语义、`counts`、入口候选、详情弹窗和诊断摘要）。候选必须限定在可见前景层，并同时满足：

1. 工作流批量完成或部分失败等可见语义；
2. 总数、成功数、失败数可从同一作用域可靠解析；
3. “确认”或“查看详情”至少一个入口可见且可交互。

扫描复用现有跨主页面和子 frame 的可见性、前景层和 pointer 可达性规则。统计标签优先于通用数字文本；同一作用域出现歧义时返回 `evidence_unavailable`，不得猜测。实现不把 `.error-content` 当作充分条件，从而避免误识别上传错误容器。

考虑过直接复用标准 `dialog` 绑定或只按 CSS 类名查找，但外层不是标准 TinperNext Modal，且实现类名在其他错误容器中复用；独立快照边界能保留外层和内层的层级，同时适配前端共享组件的标记变化。

### 3. 由 executor 管理“点击后待断言”状态

在统一点击动作完成、页面提示捕获之后，executor 使用 runtime 的观察边界检查是否出现结果层，并把快照附加到动作结果。若结果层出现，只有紧接的下一步为 `workflow_result.assert` 时才允许当前点击步骤继续保持成功；否则按现有未处理错误保护的模式把当前用例置为验证阻断，错误中包含统计和页面证据。该保护不自动执行断言。

`workflow_result.assert` 成功后记录当前结果层身份和已断言快照；`details`、`confirm` 必须验证同一结果层已完成断言，否则立即失败。结果层统计不符合预期时使用现有 `BusinessAssertionMismatch`/`observation.assertion_receipt` 路径，失败后停止用例；找不到结果层或统计不可解析则分别归类为 `target_unavailable` 或 `evidence_unavailable`。

这种状态机保留“显式断言”语义，也避免用户写 `details` 或 `confirm` 时绕过业务结果校验。全部成功路径没有结果层时不设置待断言状态，已有 `notification.assert` 行为不变。

### 4. 分层操作复用现有前景和轮询机制

`details` 只在已断言的外层根内点击“查看详情”，使用现有步骤 deadline 和语义轮询等待标准详情弹窗及可见明细稳定，并把单据编码、错误原因、错误码（页面提供时）写入 `data.workflow_result.details`。内层弹窗的“确定”继续交给既有 `dialog.confirm`，其作用域由前景弹窗规则限定。

`confirm` 只点击已断言外层根内的“确认”，随后轮询确认该根不再可见；不把点击成功当作关闭成功，也不自动恢复上一层模板。所有操作复用现有 timeout，不引入固定等待。

### 5. 报告和能力声明采用增量字段

结果层步骤的成功和失败结果都使用 `data.workflow_result`，其中按可用性保留 `semantics`、`counts`、`details`、入口状态、生命周期状态和诊断摘要。断言步骤继续生成与表单/表格断言相同形状的 `assertion_receipt`，`expected` 只含 DSL 声明字段，`actual` 含完整可解析统计。

将 `workflow_result` 加入能力注册的 available 集合；运行上下文维护本次实际执行过的组件集合，只有执行任一结果层步骤后才把它加入 enabled。这样 doctor 能发现能力，旧用例不会因为未使用该组件而虚报启用，也不需要额外开关。已有能力字段的排序和其他成员保持兼容。

### 6. 以共享组件证据驱动测试和示例

补充 DSL 示例和 schema/解析测试，覆盖整数校验、空断言、未知 target 字段、三种操作和前置顺序；用 fake runtime 覆盖识别、统计不匹配、未声明保护、详情采集、分层关闭和全部成功通知路径；用运行时 DOM fixture 覆盖同名 `.error-content` 的排除及主页面/子 frame 前景选择。实现完成后使用一个真实工作流 DSL 验证结果层，并将报告作为临时验证证据而非仓库文件提交。

## Risks / Trade-offs

- [前端文案或统计布局变化] → 组合语义、标签统计和入口状态识别；解析失败时报告 `evidence_unavailable`，不静默放行。
- [页面同时存在多个错误容器] → 所有查找限制在可见前景结果层作用域，禁止只按 `.error-content` 或全页面裸文本匹配。
- [外层和内层都存在“确定/确认”] → `details` 保存外层身份，内层关闭沿用 `dialog.confirm`，外层关闭只从外层根点击并验证根消失。
- [旧能力快照测试依赖固定集合] → 将能力注册和实际启用逻辑集中修改，并同步更新 doctor、run metadata 和相关测试的契约断言。
- [详情表格字段不稳定] → 第一版只采集页面实际提供的单据编码、错误原因和错误码，不承诺详情行级 DSL 断言。
- [结果层出现时间早于提示捕获完成] → 在现有动作完成轮询结束后用同一 step deadline 做短语义轮询，避免固定 sleep 并保留动作证据。

## Migration Plan

1. 先落地 DSL schema、runtime 快照边界、executor 状态和报告/能力契约，并补充聚焦测试与示例。
2. 使用现有工作流批量真实 DSL 验证：部分失败必须显式 `workflow_result.assert`，需要时执行 `details`、`dialog.confirm`、`workflow_result.confirm`；全部成功仍只断言通知。
3. 发布后旧 DSL 无需迁移；只有实际遇到工作流结果层的用例需要增加显式步骤。若回滚，移除新组件分派和能力声明即可，其他组件 DSL 与前端无需回滚。
