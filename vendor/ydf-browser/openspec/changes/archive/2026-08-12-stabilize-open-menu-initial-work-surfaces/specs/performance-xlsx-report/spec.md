## ADDED Requirements

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

## MODIFIED Requirements

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
