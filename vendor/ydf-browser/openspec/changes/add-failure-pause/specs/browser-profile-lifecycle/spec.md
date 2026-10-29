## MODIFIED Requirements

### Requirement: 临时浏览器上下文回退
系统 SHALL 提供 `--no-persistent-profile` 让真实浏览器运行回到每个用例使用临时浏览器上下文的隔离语义。除显式触发失败现场暂停外，系统 SHALL 在用例结束后关闭临时浏览器上下文；失败现场暂停期间 SHALL 延后关闭，直到用户结束检查。

#### Scenario: 使用临时浏览器上下文
- **WHEN** 用户运行 `ydf-browser run --dsl suite.yaml --no-persistent-profile`
- **THEN** 系统 SHALL 为每个真实用例创建不持久化的临时浏览器上下文
- **AND** 未触发失败现场暂停时，用例结束后 SHALL 关闭该临时浏览器上下文

#### Scenario: 失败现场暂停延后关闭临时上下文
- **WHEN** 用户使用 `--no-persistent-profile --pause-on-failure`，且具有可检查页面的 DSL 步骤失败触发暂停
- **THEN** 系统 MUST 在暂停期间保留该用例的临时浏览器上下文和业务页面
- **AND** 用户按 Enter 时系统 MUST 关闭该临时浏览器上下文
- **AND** 用户主动关闭业务页面或浏览器时系统 MUST 自动结束暂停

#### Scenario: 隔离模式不写默认 profile
- **WHEN** 用户使用 `--no-persistent-profile` 执行真实浏览器用例
- **THEN** 系统 SHALL NOT 写入默认持久化浏览器 profile 目录

### Requirement: 页面生命周期隔离
持久化浏览器 profile 模式下，一次 `run` SHALL 复用同一个 browser/profile；每次 `open_menu` MUST 使用新的业务 page，并关闭旧业务 page。除显式触发失败现场暂停外，每个用例结束后 MUST 关闭本用例打开的所有业务 page，同时 MUST 保留一个 run-scope page 使当前 context 可供后续用例继续使用；失败现场暂停期间 MUST 保留失败业务 page，直到用户结束检查。page 交接期间共享 context MUST NOT 进入零 page 状态。

#### Scenario: 每次 open_menu 使用新 page
- **WHEN** 同一用例中第二次执行 `open_menu`
- **THEN** 系统 MUST 先创建新的业务 page，再关闭前一次 `open_menu` 使用的 page
- **AND** 系统 MUST 使用新 page 打开新的菜单
- **AND** 交接期间共享 context MUST 始终至少包含一个可用 page

#### Scenario: 用例结束关闭 pages
- **WHEN** 一个未触发失败现场暂停的真实用例执行结束
- **THEN** 系统 MUST 先创建一个不承载该用例业务状态的 run-scope page
- **AND** 系统 MUST 关闭该用例中由 ydf-browser 打开的所有业务 pages
- **AND** 系统 SHALL 保留当前 run 的 browser/context/profile 和 run-scope page 供后续用例继续使用

#### Scenario: 失败现场暂停保留业务 pages
- **WHEN** 持久化 profile 用例因具有可检查页面的 DSL 步骤失败而触发失败现场暂停
- **THEN** 系统 MUST 在暂停期间保留该用例的失败业务 page
- **AND** 系统 MUST NOT 为后续用例创建 run-scope page 或继续调度用例
- **AND** 用户按 Enter 时系统 MUST 关闭失败业务 page 和共享 context
- **AND** 用户主动关闭失败业务 page 或浏览器时系统 MUST 自动结束暂停

#### Scenario: 下一用例替换 run-scope page
- **WHEN** 后续用例在同一持久化 context 中执行第一个 `open_menu`
- **THEN** 系统 MUST 先创建新的业务 page，再关闭前一用例保留的 run-scope page
- **AND** 系统 MUST NOT 复用前一用例的业务 page 或页面状态

#### Scenario: run 结束关闭共享 context
- **WHEN** 持久化 profile 的整个 `run` 结束
- **THEN** 系统 MUST 关闭共享 context 及其剩余 page
