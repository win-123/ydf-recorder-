## ADDED Requirements

### Requirement: 表格行值捕获 DSL
系统 SHALL 支持 `table.capture_row_values` 组件操作，用于声明从某个表格匹配行读取列值并写入运行期变量。

#### Scenario: 接受 capture_row_values 基本写法
- **WHEN** DSL 包含 `component: table`、`operation: capture_row_values`
- **AND** `target.match.column` 为 `项目名称`
- **AND** `target.match.equals` 为 `ys测试001`
- **AND** `target.capture` 为 `{yjxm.project_code: 项目代码}`
- **THEN** DSL validation MUST 接受该步骤
- **AND** `target.capture` MUST 被解释为 `变量名: 页面列名`

#### Scenario: capture 不能为空
- **WHEN** DSL 包含 `table.capture_row_values`
- **AND** `target.capture` 缺失或为空对象
- **THEN** DSL validation MUST 在业务步骤执行前失败
- **AND** 错误信息 MUST 说明必须声明至少一个捕获变量和来源列

#### Scenario: 来源列必须是字符串列名
- **WHEN** DSL 的 `target.capture` 中某个来源列不是字符串
- **THEN** DSL validation MUST 失败
- **AND** 错误信息 MUST 标识非法的 capture 来源列

### Requirement: 捕获行匹配与表格作用域
系统 SHALL 复用现有表格行定位和表格作用域规则，在目标表格内定位唯一业务行后再读取列值。

#### Scenario: 按项目名称定位行并捕获项目代码
- **WHEN** 测试集执行 `table.capture_row_values`
- **AND** `target.match.column` 为 `项目名称`
- **AND** `target.match.equals` 为 `ys测试001`
- **AND** `target.capture` 声明 `yjxm.project_code: 项目代码`
- **AND** 当前表格存在一行业务数据的 `项目名称` 为 `ys测试001` 且 `项目代码` 为 `360000241010010000013`
- **THEN** runtime MUST 定位该业务行
- **AND** executor MUST 将 `yjxm.project_code` 写入 suite 运行期变量上下文，值为 `360000241010010000013`

#### Scenario: 多表格页面使用 target.table 限定来源
- **WHEN** 当前页面存在多张可见主表格
- **AND** DSL 的 `table.capture_row_values` 填写 `target.table`
- **THEN** executor MUST 将行匹配和列值采集限定在该表格作用域内
- **AND** runtime MUST NOT 从其它表格读取同名列值

#### Scenario: 多表格页面无法唯一确定表格时失败
- **WHEN** 当前页面存在多张可见主表格
- **AND** DSL 的 `table.capture_row_values` 未填写 `target.table`
- **AND** executor 无法通过 `target.match.column` 和捕获来源列唯一确定目标表格
- **THEN** 步骤 MUST 在读取任何值前失败
- **AND** 错误信息 MUST 要求补充 `target.table`

#### Scenario: 树形表格折叠子行可捕获
- **WHEN** 目标业务行位于折叠树形表格子节点下
- **AND** `table.capture_row_values` 提供的 `match` 能唯一定位该业务行
- **THEN** runtime MUST 在目标表格内展开、滚动并重查目标行
- **AND** runtime MUST 在找到目标行后读取捕获来源列
- **AND** 步骤结果 MUST 包含 `row_search` 诊断

### Requirement: 捕获值写入
系统 SHALL 将捕获到的非空列值写入当前 suite 运行期变量上下文，并在同一步中支持一次捕获多个变量。

#### Scenario: 一次捕获多个列值
- **WHEN** `target.capture` 包含 `yjxm.project_code: 项目代码` 和 `yjxm.project_name: 项目名称`
- **AND** 目标行中 `项目代码` 为 `3600001`
- **AND** 目标行中 `项目名称` 为 `ys测试001`
- **THEN** executor MUST 同时写入 `yjxm.project_code = 3600001` 和 `yjxm.project_name = ys测试001`

#### Scenario: 捕获值为空时失败
- **WHEN** 目标行存在
- **AND** `target.capture` 的某个来源列存在但读取到的文本为空
- **THEN** 步骤 MUST 失败
- **AND** executor MUST NOT 将该空值写入 suite 运行期变量上下文

#### Scenario: 来源列不存在时失败
- **WHEN** 目标行存在
- **AND** `target.capture` 引用的来源列在目标表格中不存在
- **THEN** 步骤 MUST 失败
- **AND** 错误信息 MUST 包含缺失的来源列名

#### Scenario: 捕获失败不产生部分变量污染
- **WHEN** 同一个 `capture_row_values` 步骤声明多个捕获变量
- **AND** 其中一个来源列读取失败或值为空
- **THEN** 该步骤 MUST 整体失败
- **AND** executor MUST NOT 写入该步骤声明的任何捕获变量

### Requirement: 捕获报告数据
系统 SHALL 在捕获步骤结果中记录可审计数据，说明变量来自哪个表格、哪个匹配行和哪个来源列。

#### Scenario: 成功捕获后记录 captured 和 sources
- **WHEN** `table.capture_row_values` 成功捕获 `yjxm.project_code`
- **THEN** 步骤结果 MUST 包含 `data.captured.yjxm.project_code`
- **AND** 步骤结果 MUST 包含 `data.capture_sources.yjxm.project_code = 项目代码`
- **AND** 步骤结果 MUST 包含解析后的 `match`

#### Scenario: 指定表格时记录表格诊断
- **WHEN** `table.capture_row_values` 使用 `target.table`
- **THEN** 步骤结果 MUST 包含 `data.table`
- **AND** 如果 executor 解析出表格 fieldid，步骤结果 MUST 包含 `data.table_fieldid`

#### Scenario: 捕获失败时保留诊断
- **WHEN** `table.capture_row_values` 因未找到匹配行、来源列缺失或捕获值为空失败
- **THEN** 步骤错误数据 MUST 包含目标 `match`
- **AND** 步骤错误数据 MUST 包含声明的 `capture` 映射
- **AND** 如果触发表格遍历，步骤错误数据 MUST 包含 `row_search` 诊断
