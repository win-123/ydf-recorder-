## Context

`open_menu` 当前通过 `/#/service/<serviceCode>` 打开菜单、等待页面就绪并校验菜单页签，然后抓取 `page_state.frames`。报告虽然已有 frame 名称和 URL，但没有把它们与当前菜单身份关联，也没有形成可直接使用的菜单承载方式结论。

真实对比表明：

- “交易类型参数设置”的主页面下存在一级业务 frame，frame `name` 等于菜单 `service_code`，frame URL 指向菜单 `service_url`；同页还存在无关的 `helper_iframe-*`。
- “规则管理”的主页面下只有无关的 `helper_iframe-*`，业务内容直接渲染。

识别必须同时适用于单据页和非单据模板页面，不能依赖模板获取或 manifest 构建是否成功。

## Goals / Non-Goals

**Goals:**

- 每次 `open_menu` 自动形成 `iframe`、`direct` 或 `unknown` 结论。
- 只识别当前菜单的主业务承载 frame，避免局部或嵌套 iframe 误判。
- 在现有 JSON 和 HTML 报告中提供可用于填写 bug 单的稳定证据。
- 保持现有菜单打开和非单据模板页面 open-only 语义。

**Non-Goals:**

- 不新增显式检测或断言类 DSL 动作。
- 不自动创建 bug 单、截图、保存整页 DOM 或新增汇总报告结构。
- 不按是否存在单据模板推断菜单承载方式。

## Decisions

### Decision: 由运行时按菜单身份识别一级业务 frame

在 `PlaywrightRuntime` 的共享入口增加菜单承载方式检查，输入当前 `MenuTarget`，输出结构化检测结果。运行时只检查主页面直接承载的一级子 frame，不递归扫描业务 frame 内部结构；候选必须通过 frame `name` 与 `service_code` 对应，或通过规范化后的 frame URL 与 `service_url` 对应。

先排除主 frame、业务助手等已知非菜单业务 frame，再进行身份匹配。唯一匹配返回 `iframe`；页面就绪并通过菜单页签校验后没有匹配返回 `direct`；检查异常或多个冲突候选返回 `unknown` 并保留原因。

替代方案是按 `frame_count > 1` 判断。真实页面始终可能包含 `helper_iframe-*`，该方案会把已经直接渲染的“规则管理”误判为 iframe，因此不采用。

### Decision: 检测与模板支持状态解耦

执行器在菜单打开和页签校验完成后调用运行时检测。检测可以利用 `fetch_template` 过程中补齐到 `MenuTarget` 的 `service_url`，但不得以模板获取成功、manifest 是否存在或 `template_supported` 值作为分类条件。

替代方案是把非单据模板页面视为 iframe、单据页视为 direct。两个概念描述的维度不同，且无法覆盖改造过程中的组合，因此不采用。

### Decision: 复用现有 open_menu 结果和报告通道

`open_menu` 的 `data` 增加 `menu_hosting` 对象，至少包含 `mode`；`iframe` 结果增加 `frame_name` 和 `frame_url`，菜单完整路径和 `service_code` 继续复用已有 `menu_target`；`unknown` 结果增加 `reason`。成功消息追加承载方式，使现有 HTML 报告无需展开成功步骤的 `data` 也能看到结论。

`iframe` 和 `unknown` 都不改变 `open_menu` 成功状态。菜单是否打开仍由现有页面就绪与页签校验决定，承载方式只提供迁移检查证据。

替代方案是新增 DSL 断言或让 iframe 菜单打开失败。两者都会改变已有用例语义，并把“打开成功”和“改造完成”混成同一个判断，因此不采用。

### Decision: 使用共享分类测试和两个真实菜单验收

聚焦测试覆盖唯一业务 frame、无业务 frame、业务助手排除、嵌套 frame 排除、多个冲突候选和检查异常。真实验证继续使用“交易类型参数设置”和“规则管理”，分别证明 `iframe` 与 `direct`，并检查 JSON/HTML 展示。

## Risks / Trade-offs

- [Risk] 菜单 service URL 带动态查询参数，逐字比较会漏掉业务 frame。→ Mitigation：比较稳定的 frame 名称和规范化 URL，不依赖时间戳或查询参数顺序。
- [Risk] 页面延迟创建业务 iframe，缺失候选可能被判为 `direct`。→ Mitigation：检测复用现有页面就绪等待和菜单页签校验，不增加任意固定睡眠；真实验收覆盖当前 iframe 菜单。
- [Risk] 新出现的工作台辅助 frame 与菜单身份冲突。→ Mitigation：多个候选返回 `unknown`，不得任选或默认为 `direct`。
- [Trade-off] 不增加套件级 iframe 菜单汇总。→ 每个 `open_menu` 成功消息和结构化结果已经可见；只有现有报告消费方式被证明不足时再增加汇总。
