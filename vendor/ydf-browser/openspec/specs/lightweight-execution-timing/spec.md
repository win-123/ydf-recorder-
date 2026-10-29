# lightweight-execution-timing Specification

## Purpose
定义真实 DSL 普通运行中的轻量步骤、用例准备和菜单阶段计时，以及与性能模式和现有报告消费者的兼容边界。
## Requirements
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
`open_menu` SHALL 在普通报告中记录菜单解析、浏览器打开、菜单页签就绪、页面初始模板响应等待、manifest 构建、首次展示工作面等待和绑定等实际发生阶段的耗时，并单独记录浏览器触发到界面稳定的菜单业务稳定耗时。

#### Scenario: 单据模板菜单打开成功
- **WHEN** `open_menu` 成功打开支持单据模板的菜单
- **THEN** `data.timing.phases` MUST 包含实际执行的菜单解析、页面打开、菜单就绪、初始模板响应等待、manifest 构建、首次展示工作面等待和绑定阶段
- **AND** `data.timing.phases` MUST NOT 记录未执行的浏览器触发前模板获取阶段
- **AND** `data.timing.menu_business_stable_ms` MUST 表示浏览器实际触发菜单到全部首次展示工作面稳定的墙钟耗时

#### Scenario: 页面模板请求属于菜单业务稳定耗时
- **WHEN** 菜单页面在浏览器触发后请求服务详情和初始模板
- **THEN** 页面请求、模板响应等待、manifest 构建及首次工作面等待 MUST 包含在 `menu_business_stable_ms` 中
- **AND** 菜单路径解析等浏览器触发前准备 MUST 仅进入自动化步骤总耗时和对应阶段耗时

#### Scenario: 触发前准备不污染业务耗时
- **WHEN** 系统在浏览器触发前解析目标菜单
- **THEN** 菜单解析耗时 MUST 进入自动化步骤总耗时和对应阶段耗时
- **AND** 菜单解析耗时 MUST NOT 进入 `menu_business_stable_ms`
- **AND** 页面模板请求及 manifest 构建 MUST 在浏览器触发后执行并进入 `menu_business_stable_ms`

#### Scenario: 模板响应在菜单页签就绪前已经完成
- **WHEN** 页面初始模板响应已被运行时捕获且 `open_menu` 开始消费时无需额外等待
- **THEN** 初始模板响应等待阶段 MUST 记录实际消耗时间并允许为零
- **AND** 系统 MUST NOT 为形成非零指标而增加固定等待

#### Scenario: 非单据模板页面打开成功
- **WHEN** 页面实际服务元数据明确认定目标为非单据页面且 `open_menu` 按 open-only 语义成功
- **THEN** `data.timing.phases` MUST 记录菜单解析、页面打开、菜单就绪和页面类型判定等实际阶段
- **AND** 不存在的 manifest 构建、工作面等待或绑定阶段 MUST NOT 伪造非零耗时

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
