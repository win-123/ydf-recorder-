## ADDED Requirements

### Requirement: open_menu 识别稳定空内容卡片终态

在单据模板菜单的首次展示工作面集合中，运行时可见的 `content_card` 若没有局部加载状态、业务错误、可见字段、可交互控件、可见文本或明确空态文本，且该内容快照在共享稳定窗口内保持不变，`open_menu` MUST 将其视为合法的空内容初始终态。系统 MUST 在结构化工作面证据中保留该卡片，并以 `empty_content=true` 区分空内容终态与普通非空卡片。

#### Scenario: 可见空卡片在稳定窗口后完成

- **WHEN** `content_card` 已在当前 frame 可见，`busy=0` 且没有错误证据、字段、交互控件、文本或显式空态
- **AND** 上述内容快照连续稳定至少 500ms
- **THEN** `open_menu` MUST 将该工作面标记为 `terminal=true` 和 `empty_content=true`
- **AND** 若其它首次展示工作面也已进入终态，`open_menu` MUST 使用现有稳定快照完成信号继续执行

#### Scenario: 空卡片存在加载或错误状态

- **WHEN** 空 `content_card` 存在可见局部加载状态、重叠页面加载状态或业务错误证据
- **THEN** 该工作面 MUST 保持 `terminal=false`
- **AND** `open_menu` MUST 继续等待或按现有失败语义报告错误

#### Scenario: 空卡片在稳定窗口内出现内容

- **WHEN** 空 `content_card` 在 `open_menu` 报告成功前出现字段、交互控件、文本、显式空态或加载状态
- **THEN** 系统 MUST 使原稳定窗口失效并重新评估该工作面
- **AND** 系统 MUST NOT 使用变化前的空内容快照提前完成 `open_menu`

#### Scenario: 空卡片发生显隐变化

- **WHEN** 空 `content_card` 在等待期间隐藏、消失或重新出现
- **THEN** 系统 MUST 按当前运行时可见工作面集合重新计算终态
- **AND** 系统 MUST NOT 将旧卡片快照作为当前页面的完成证据

#### Scenario: 非卡片空容器不适用空内容语义

- **WHEN** 页面根、普通祖先容器或其它非 `content_card` 工作面可见但没有内容
- **THEN** 系统 MUST NOT 仅因其为空而应用 `empty_content=true` 的终态规则
- **AND** 系统 MUST 继续使用该工作面类型既有的就绪判定语义
