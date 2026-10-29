## ADDED Requirements

### Requirement: 性能报告区分 profile cache mode
系统 SHALL 在性能报告中使用能区分持久化浏览器 profile、临时浏览器上下文和同用例重新打开菜单的 cache mode 语义。

#### Scenario: 持久化 profile 首次打开菜单
- **WHEN** 用例在默认持久化浏览器 profile 模式下首次执行 `open_menu`
- **THEN** 性能报告 SHALL 将该打开菜单阶段标识为 `persistent_profile_case_open_menu`

#### Scenario: 持久化 profile 同用例重新打开菜单
- **WHEN** 性能模式为了采集 warm 指标，在同一用例和同一持久化 profile 中重新打开菜单
- **THEN** 性能报告 SHALL 将该阶段标识为 `persistent_profile_same_case_reopen_menu`

#### Scenario: 临时上下文首次打开菜单
- **WHEN** 用例在 `--no-persistent-profile` 模式下首次执行 `open_menu`
- **THEN** 性能报告 SHALL 将该打开菜单阶段标识为 `ephemeral_case_open_menu`

#### Scenario: 临时上下文同用例重新打开菜单
- **WHEN** 性能模式为了采集 warm 指标，在同一临时浏览器上下文中重新打开菜单
- **THEN** 性能报告 SHALL 将该阶段标识为 `ephemeral_same_context_reopen_menu`

#### Scenario: 工作簿保留 cache mode
- **WHEN** 性能数据被导出到 `performance.xlsx`
- **THEN** 工作簿 SHALL 在运行汇总、用例汇总或相关明细中保留上述 cache mode
- **AND** 工作簿 SHALL NOT 将默认持久化 profile 打开菜单误标为旧的 `cold_ephemeral`
