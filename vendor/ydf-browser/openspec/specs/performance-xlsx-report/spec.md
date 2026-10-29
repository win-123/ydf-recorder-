# performance-xlsx-report Specification

## Purpose
定义性能模式 JSON 与 Excel 工作簿的生成、步骤和网络请求归因、菜单业务稳定耗时及兼容语义。

## Requirements
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

#### Scenario: 步骤耗时区分自动化墙钟时间和完成信号等待
- **WHEN** 系统为已执行步骤生成步骤总览行
- **THEN** 总耗时列 MUST 标识为自动化步骤总耗时，并表示定位、动作执行、完成等待和后续校验在内的步骤墙钟时间
- **AND** 该行 MUST 分别输出完成信号等待、总耗时扣除等待后的动作处理耗时、完成信号、兼容兜底和最慢 API 请求耗时
- **AND** 最慢 API 请求耗时 MUST 作为可能与完成等待重叠的独立参考值，MUST NOT 与其它耗时列相加解释总耗时

#### Scenario: 未执行步骤不被当成已执行
- **WHEN** 用例在某个失败步骤后停止
- **THEN** 未被执行的后续步骤 MUST NOT 作为正常步骤性能行出现
- **AND** 用例汇总 MUST 仍然说明该用例失败，并且在完成全部定义步骤前已经停止

### Requirement: 网络请求明细保留步骤上下文
系统 SHALL 在网络请求明细中保留足够的 suite、case、请求开始步骤和请求完成步骤上下文，以便把请求追溯到触发它的业务操作并识别跨步骤完成。

#### Scenario: 请求明细行包含步骤身份
- **WHEN** 性能运行期间捕获到浏览器网络请求
- **THEN** 网络请求明细 sheet MUST 包含关联的 suite code、case code、开始步骤序号、开始动作标签、完成步骤序号、完成动作标签、URL、HTTP method、resource type、category、status、duration、encoded body size 和 failed 标记

#### Scenario: 跨步骤请求保留开始步骤归因
- **WHEN** 一个请求在某个 DSL 步骤中开始，并在后续步骤开始后才完成
- **THEN** 该请求 MUST 归因到它开始时所在的步骤
- **AND** 请求明细 MUST 记录实际完成步骤
- **AND** 该请求 MUST NOT 被静默计入后续步骤的请求统计

#### Scenario: 步骤结束后在空闲上下文完成
- **WHEN** 一个后台请求在启动步骤结束后、没有其它步骤正在执行时完成
- **THEN** 请求明细 MUST 保留开始步骤归因
- **AND** 完成步骤 MUST 标记为空闲或 unknown，而不是伪造后续步骤

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

### Requirement: 性能报告单独呈现菜单业务稳定耗时
系统 SHALL 在性能 JSON 和 `performance.xlsx` 步骤总览中单独呈现 `open_menu` 从浏览器触发到首次展示工作面稳定的菜单业务稳定耗时，并继续保留自动化步骤总耗时。

#### Scenario: 自动列表查询属于 open_menu
- **WHEN** 业务代码在打开菜单时自动执行初始列表查询
- **THEN** 查询等待和渲染 MUST 包含在 `open_menu` 的菜单业务稳定耗时中
- **AND** 查询请求 MUST 按其启动步骤归属于 `open_menu`

#### Scenario: 自动化准备和业务耗时分列
- **WHEN** 性能工作簿输出 `open_menu` 步骤
- **THEN** 步骤总览 MUST 分别输出自动化步骤总耗时和菜单业务稳定耗时
- **AND** 两个耗时 MUST NOT 被解释为需要相加的串行指标

### Requirement: 性能采集记录步骤请求上传量
系统 SHALL 为性能采集期间的每个网络请求记录请求体字节数或明确的不可用状态，并按请求启动时所在步骤聚合步骤上传量。

#### Scenario: 请求上传量可测量
- **WHEN** 归属于某个步骤的全部请求都能取得请求体大小
- **THEN** 底层报告 MUST 为每个请求保留请求体字节整数
- **AND** 步骤上传量 MUST 等于这些请求体字节数之和
- **AND** Excel `上传KB` MUST 只在导出时从字节换算

#### Scenario: 无请求体的方法计为零
- **WHEN** 一个 `GET` 或 `HEAD` 请求没有请求体大小证据
- **THEN** 该请求的上传字节数 MUST 记为 0
- **AND** 该值 MUST 参与其启动步骤的上传量聚合

#### Scenario: 步骤上传量不可完整测量
- **WHEN** 某个归属于步骤的请求无法取得请求体大小
- **THEN** 报告 MUST 标记上传量不可用并给出原因
- **AND** Excel `上传KB` MUST 留空而不是写入 0

#### Scenario: 跨步骤请求保留上传量归因
- **WHEN** 一个请求在某个步骤中启动并在后续步骤中完成或失败
- **THEN** 该请求的上传字节数或不可用状态 MUST 归属于启动步骤
- **AND** 系统 MUST NOT 将其上传量计入后续步骤

#### Scenario: 浏览器关闭取消响应大小读取
- **WHEN** 响应回调读取 Playwright request size 时发生取消
- **THEN** 系统 MUST 回退使用响应 `Content-Length`
- **AND** 该取消 MUST NOT 产生未处理的回调异常或改变业务结果

#### Scenario: 请求体内容不进入性能数据
- **WHEN** 系统取得请求体大小
- **THEN** 性能数据 MUST 只保存字节数或不可用原因
- **AND** 系统 MUST NOT 为计算上传量而把请求体内容写入事件、错误文本、控制台、性能工作簿、`report.json` 或 `report.html`

### Requirement: 性能采集记录步骤结束时的页面 JS 堆
系统 SHALL 在每个实际执行步骤的动作耗时停止计时后，采集顶层页面当时的 JS 堆已用量，并将其作为可选步骤指标输出。

#### Scenario: JS 堆快照可用
- **WHEN** 一个成功或失败步骤结束且顶层页面支持读取 `performance.memory.usedJSHeapSize`
- **THEN** 底层报告 MUST 保存该步骤的 JS 堆已用字节数
- **AND** Excel `JS堆已用(MB)` MUST 以 MB 显示并保留两位小数
- **AND** 指标采集耗时 MUST NOT 计入该步骤的动作耗时

#### Scenario: BPR 控制步骤采集 JS 堆快照
- **WHEN** 开启性能采集的运行完成一个实际执行的 `bpr.start` 或 `bpr.stop` 步骤
- **THEN** 系统 MUST 按与业务步骤相同的规则采集该控制步骤结束时的 JS 堆已用量

#### Scenario: JS 堆快照不可用
- **WHEN** 步骤结束时没有页面、页面已经关闭或浏览器不支持该指标
- **THEN** 系统 MUST 记录 JS 堆快照不可用状态和原因
- **AND** Excel `JS堆已用(MB)` MUST 留空
- **AND** 指标不可用 MUST NOT 改变步骤或业务用例结果

#### Scenario: JS 堆指标不表示峰值或增量
- **WHEN** 报告输出步骤 JS 堆已用量
- **THEN** 该值 MUST 表示步骤结束时顶层页面的单次快照
- **AND** 系统 MUST NOT 将其描述为页面内存峰值、步骤增量、iframe 总量或浏览器进程 RSS

### Requirement: 步骤总览排列上传下载和内存指标
系统 SHALL 在性能工作簿步骤总览中以固定顺序展示步骤上传量、下载量、JS 堆已用量和最慢请求。

#### Scenario: 步骤总览输出新增指标
- **WHEN** 性能数据被导出到 `performance.xlsx`
- **THEN** 步骤总览 MUST 按 `上传KB`、`下载KB`、`JS堆已用(MB)`、`最慢请求` 的顺序排列相关列
- **AND** 明确不可用的上传量和 JS 堆值 MUST 留空而不是使用 0 冒充
