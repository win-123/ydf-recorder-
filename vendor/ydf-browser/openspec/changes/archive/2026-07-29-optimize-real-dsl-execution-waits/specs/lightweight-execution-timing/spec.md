## ADDED Requirements

### Requirement: 普通报告默认记录步骤耗时
系统 SHALL 在未开启 `--performance` 的普通真实运行中，为每个实际执行的 DSL 步骤记录轻量执行计时。

#### Scenario: 普通步骤执行成功
- **WHEN** 一个 DSL 步骤在普通模式下执行成功
- **THEN** 步骤数据 MUST 在 `data.timing.duration_ms` 记录该步骤总耗时

#### Scenario: 普通步骤执行失败
- **WHEN** 一个 DSL 步骤在普通模式下执行失败
- **THEN** 失败步骤数据 MUST 在 `data.timing.duration_ms` 记录失败前已消耗的时间
- **AND** 未执行的后续步骤 MUST NOT 产生正常步骤计时

### Requirement: 普通报告记录用例准备耗时
系统 SHALL 在用例报告的 `timing.setup` 中记录浏览器启动、登录和用户上下文准备阶段的轻量耗时证据。

#### Scenario: 用例准备成功
- **WHEN** 真实用例完成浏览器启动、登录、租户、默认组织和业务年度上下文准备
- **THEN** 用例报告 MUST 记录实际发生的准备阶段及其 `duration_ms`

#### Scenario: 用例准备失败
- **WHEN** 真实用例在登录或上下文准备阶段失败
- **THEN** 失败报告 MUST 记录已经完成的阶段、失败阶段和失败前耗时
- **AND** 报告 MUST 保留原始错误类型和消息

### Requirement: 打开菜单记录分阶段耗时
`open_menu` SHALL 在普通报告中记录菜单解析、浏览器打开、菜单就绪、模板获取、manifest 构建和绑定等实际发生阶段的耗时。

#### Scenario: 单据模板菜单打开成功
- **WHEN** `open_menu` 成功打开支持单据模板的菜单
- **THEN** `data.timing.phases` MUST 包含实际执行的菜单解析、页面打开、菜单就绪、模板获取、manifest 构建和绑定阶段

#### Scenario: 非单据模板页面打开成功
- **WHEN** `open_menu` 成功打开非单据模板页面
- **THEN** `data.timing.phases` MUST 记录菜单解析、页面打开、菜单就绪和失败的模板获取阶段
- **AND** 不存在的 manifest 构建或绑定阶段 MUST NOT 伪造非零耗时

### Requirement: 轻量计时不启用重型性能副作用
普通报告的轻量执行计时 MUST NOT 启动网络明细、Web Vitals、BPR、性能 XLSX 或额外菜单重开。

#### Scenario: 未指定性能开关
- **WHEN** 用户执行 `ydf-browser run` 且没有指定 `--performance`
- **THEN** JSON 和 HTML 报告 SHALL 包含轻量执行计时
- **AND** 系统 MUST NOT 生成 `performance.xlsx` 或为了计时额外重开菜单

#### Scenario: 指定性能开关
- **WHEN** 用户执行 `ydf-browser run --performance`
- **THEN** 系统 SHALL 同时保留轻量执行计时和现有性能数据
- **AND** 现有网络、Web Vitals、BPR、XLSX 和 cache mode 语义 MUST 保持兼容

### Requirement: 现有报告消费者保持兼容
轻量执行计时 SHALL 作为新增字段加入现有 JSON 和 HTML 报告，现有用例总耗时、成功状态、错误和性能字段 MUST 保持原有含义。

#### Scenario: 旧消费者忽略新增字段
- **WHEN** 报告消费者只读取现有 `duration_ms`、`success`、`errors` 或 `performance` 字段
- **THEN** 新增 `timing` 字段 MUST NOT 改变这些字段的结构或语义
