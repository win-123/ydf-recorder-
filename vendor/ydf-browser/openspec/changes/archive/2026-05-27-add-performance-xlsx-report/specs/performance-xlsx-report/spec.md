## ADDED Requirements

### Requirement: 性能模式生成 Excel 工作簿
系统 SHALL 在执行 `ydf-browser run --performance` 时生成一个包含性能数据的 Excel 工作簿。

#### Scenario: 生成性能工作簿
- **WHEN** 一次运行在开启 `--performance` 后完成
- **THEN** 系统 MUST 在 `report.json` 所在报告目录创建 `performance.xlsx`
- **AND** 工作簿 MUST 包含运行汇总、用例汇总、步骤总览、网络请求明细、失败请求详情、重复调用 URL 和 Web Vitals 可用性相关 sheet

#### Scenario: 报告性能工作簿路径
- **WHEN** `performance.xlsx` 已生成
- **THEN** 系统 MUST 在 stdout 摘要、`report.json` 和 `report.html` 中包含该工作簿路径

#### Scenario: 普通运行不生成工作簿
- **WHEN** 一次运行未开启 `--performance` 并完成
- **THEN** 系统 MUST NOT 生成 `performance.xlsx`
- **AND** 普通功能测试报告结构 MUST 继续兼容现有非性能模式运行

### Requirement: 步骤总览包含每个已执行步骤
系统 SHALL 为用例结束前实际执行过的每个 DSL 步骤输出一行步骤级性能记录。

#### Scenario: 成功用例记录所有步骤
- **WHEN** 一个包含多个步骤的用例在性能模式下执行通过
- **THEN** 步骤总览 sheet MUST 为每个已执行步骤包含一行记录
- **AND** 每行 MUST 包含 suite code、case code、步骤序号、动作标签、成功状态、消息、耗时、可用时的页面标题或 URL，以及网络汇总值

#### Scenario: 失败步骤仍被记录
- **WHEN** 某个步骤在性能模式下失败
- **THEN** 步骤总览 sheet MUST 包含该失败步骤行
- **AND** 该行 MUST 包含失败状态、失败消息、已消耗耗时，以及失败前已采集到的网络数据

#### Scenario: 未执行步骤不被当成已执行
- **WHEN** 用例在某个失败步骤后停止
- **THEN** 未被执行的后续步骤 MUST NOT 作为正常步骤性能行出现
- **AND** 用例汇总 MUST 仍然说明该用例失败，并且在完成全部定义步骤前已经停止

### Requirement: 网络请求明细保留步骤上下文
系统 SHALL 在网络请求明细中保留足够的 suite、case 和 step 上下文，以便把请求追溯到触发它的业务操作。

#### Scenario: 请求明细行包含步骤身份
- **WHEN** 性能运行期间捕获到浏览器网络请求
- **THEN** 网络请求明细 sheet MUST 包含关联的 suite code、case code、步骤序号、动作标签、URL、HTTP method、resource type、category、status、duration、encoded body size 和 failed 标记

#### Scenario: 跨步骤请求保留开始步骤归因
- **WHEN** 一个请求在某个 DSL 步骤中开始，并在后续步骤开始后才完成
- **THEN** 该请求 MUST 归因到它开始时所在的步骤
- **AND** 该请求 MUST NOT 被静默计入后续步骤的请求统计

#### Scenario: 无法归因的请求单独标记
- **WHEN** 某个请求无法归因到具体 DSL 步骤
- **THEN** 请求明细 MUST 将其步骤上下文标记为 setup、warm 或 unknown
- **AND** 该请求 MUST NOT 被计入无关业务步骤的汇总数据

### Requirement: 工作簿提供排障汇总
系统 SHALL 提供汇总 sheet，帮助测试人员无需解析嵌套 JSON 就能识别慢操作或失败操作。

#### Scenario: 用例汇总聚合步骤和网络数据
- **WHEN** 性能数据被导出
- **THEN** 用例汇总 sheet MUST 包含用例状态、总耗时、已执行步骤数、总请求数、失败请求数、最慢步骤，以及可用时的 warm open menu 数据

#### Scenario: 失败请求 sheet 过滤失败项
- **WHEN** 捕获到的请求包含请求失败或 HTTP 4xx/5xx 响应
- **THEN** 失败请求详情 sheet MUST 包含这些请求的步骤上下文和错误或状态信息

#### Scenario: 重复 URL sheet 汇总重复调用
- **WHEN** 同一个 URL 在选定聚合范围内被请求超过一次
- **THEN** 重复调用 URL sheet MUST 包含该 URL、调用次数，以及关联的 run/case/step 上下文

#### Scenario: 运行汇总标识最慢记录
- **WHEN** 性能数据被导出
- **THEN** 运行汇总 sheet MUST 标识最慢用例、最慢步骤、网络失败总数和聚合请求数

### Requirement: Web Vitals 是可选增强指标
系统 SHALL 将 Web Vitals 作为可选增强指标处理，而不是每个步骤必须具备的性能数据。

#### Scenario: Web Vitals 可用
- **WHEN** runtime 能够采集页面级 LCP、CLS 或 INP 值
- **THEN** Web Vitals sheet MUST 包含采集到的数值和评级，并在可用时附带页面和步骤上下文

#### Scenario: Web Vitals 不可用
- **WHEN** runtime 无法为某次运行或步骤可靠采集 Web Vitals
- **THEN** 工作簿生成 MUST 仍然成功
- **AND** Web Vitals sheet MUST 清晰标记这些指标不可用，而不是伪造数值

### Requirement: Excel 导出使用受支持依赖
系统 SHALL 使用维护中的 Excel 写入依赖直接创建工作簿。

#### Scenario: 工作簿生成使用 openpyxl
- **WHEN** 实现性能工作簿导出能力
- **THEN** 项目 MUST 声明 `openpyxl` 为运行时依赖
- **AND** 导出器 MUST 写出有效的 `.xlsx` 文件，且不要求测试人员手工合并多份 CSV 文件

#### Scenario: 导出失败不掩盖测试结果
- **WHEN** 功能运行已经完成但工作簿生成失败
- **THEN** 报告 MUST 保留功能运行结果
- **AND** 报告 MUST 包含清晰的性能导出错误，使调用方能看到该失败
