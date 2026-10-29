## MODIFIED Requirements

### Requirement: 页面生命周期隔离
持久化浏览器 profile 模式下，一次 `run` SHALL 复用同一个 browser/profile；每次 `open_menu` MUST 使用新的业务 page，并关闭旧业务 page；每个用例结束后 MUST 关闭本用例打开的所有业务 page，同时 MUST 保留一个 run-scope page 使当前 context 可供后续用例继续使用。page 交接期间共享 context MUST NOT 进入零 page 状态。

#### Scenario: 每次 open_menu 使用新 page
- **WHEN** 同一用例中第二次执行 `open_menu`
- **THEN** 系统 MUST 先创建新的业务 page，再关闭前一次 `open_menu` 使用的 page
- **AND** 系统 MUST 使用新 page 打开新的菜单
- **AND** 交接期间共享 context MUST 始终至少包含一个可用 page

#### Scenario: 用例结束关闭 pages
- **WHEN** 一个真实用例执行结束
- **THEN** 系统 MUST 先创建一个不承载该用例业务状态的 run-scope page
- **AND** 系统 MUST 关闭该用例中由 ydf-browser 打开的所有业务 pages
- **AND** 系统 SHALL 保留当前 run 的 browser/context/profile 和 run-scope page 供后续用例继续使用

#### Scenario: 下一用例替换 run-scope page
- **WHEN** 后续用例在同一持久化 context 中执行第一个 `open_menu`
- **THEN** 系统 MUST 先创建新的业务 page，再关闭前一用例保留的 run-scope page
- **AND** 系统 MUST NOT 复用前一用例的业务 page 或页面状态

#### Scenario: run 结束关闭共享 context
- **WHEN** 持久化 profile 的整个 `run` 结束
- **THEN** 系统 MUST 关闭共享 context 及其剩余 page
