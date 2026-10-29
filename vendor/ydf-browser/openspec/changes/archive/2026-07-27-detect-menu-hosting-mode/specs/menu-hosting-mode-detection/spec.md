## ADDED Requirements

### Requirement: open_menu 自动识别菜单承载方式
系统 SHALL 在菜单真实打开、页面就绪并通过菜单页签校验后，自动将菜单承载方式识别为 `iframe`、`direct` 或 `unknown`，且不得要求 DSL 增加检测步骤或选择器。

#### Scenario: 识别 iframe 承载菜单
- **WHEN** 当前菜单的主页面存在唯一一个与菜单 `service_code` 或 `service_url` 对应的一级业务 frame
- **THEN** `open_menu` 结果中的菜单承载方式 MUST 为 `iframe`

#### Scenario: 识别直接渲染菜单
- **WHEN** 当前菜单已通过页面就绪和菜单页签校验，且主页面不存在与菜单身份对应的一级业务 frame
- **THEN** `open_menu` 结果中的菜单承载方式 MUST 为 `direct`

#### Scenario: 检查结果不确定
- **WHEN** 运行时检查 frame 失败或发现多个与菜单身份冲突的一级候选
- **THEN** `open_menu` 结果中的菜单承载方式 MUST 为 `unknown`
- **AND** 系统 MUST 记录不能确定承载方式的原因

### Requirement: 菜单承载方式只依据主业务 frame
系统 MUST 只使用主页面直接承载、且与当前菜单身份对应的一级业务 frame 判断菜单承载方式，不得因局部 iframe 或模板支持状态产生误判。

#### Scenario: 排除业务助手 iframe
- **WHEN** 直接渲染菜单的主页面同时存在 `helper_iframe-*` 等业务助手 frame
- **THEN** 系统 MUST 忽略该辅助 frame
- **AND** 菜单承载方式 MUST 保持为 `direct`

#### Scenario: 排除业务页面内部嵌套 iframe
- **WHEN** 当前菜单业务内容内部存在弹出参照、编辑器或其它嵌套 iframe
- **THEN** 系统 MUST NOT 将嵌套 iframe 作为菜单主业务承载 frame

#### Scenario: 识别结果与单据模板解耦
- **WHEN** `fetch_template` 或 manifest 构建成功或失败
- **THEN** 系统 MUST 继续仅依据运行时一级业务 frame 与菜单身份的对应关系确定承载方式

### Requirement: 报告提供菜单承载方式和提单证据
系统 SHALL 在现有 `open_menu` 结构化结果和人类可读报告中展示菜单承载方式，同时保持菜单打开成功语义不变。

#### Scenario: iframe 结果记录证据
- **WHEN** 菜单承载方式为 `iframe`
- **THEN** `open_menu` 结构化结果 MUST 记录 `mode`、业务 frame 名称和业务 frame URL
- **AND** 结果 MUST 能通过现有 `menu_target` 取得菜单完整路径和 `service_code`

#### Scenario: HTML 报告展示识别结果
- **WHEN** `open_menu` 成功并生成 HTML 报告
- **THEN** 成功步骤消息 MUST 显示 `iframe`、`direct` 或 `unknown` 承载方式

#### Scenario: iframe 不改变菜单打开成功状态
- **WHEN** 菜单真实打开并通过页签校验且承载方式为 `iframe`
- **THEN** `open_menu` 步骤 MUST 保持成功

#### Scenario: unknown 不改变菜单打开成功状态
- **WHEN** 菜单真实打开并通过页签校验但承载方式为 `unknown`
- **THEN** `open_menu` 步骤 MUST 保持成功
- **AND** 系统 MUST NOT 将该结果默认为 `direct` 或自动标记为待提 bug
