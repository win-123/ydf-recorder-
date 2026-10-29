## ADDED Requirements

### Requirement: 表格列集合断言
系统 SHALL 支持 `table.assert_columns` 断言当前表格 DOM 中实际可到达的表头列集合。

#### Scenario: 断言指定表格不存在目标列
- **WHEN** DSL 文档执行 `table.assert_columns`，且 `target.table` 为 `三级模板明细`、`target.absent` 包含 `一级绩效指标分值` 和 `二级绩效指标分值`
- **THEN** executor MUST 将 `三级模板明细` 解析为目标表格作用域
- **THEN** runtime MUST 采集该表格实际 DOM 表头
- **THEN** 如果实际表头不包含 `一级绩效指标分值` 和 `二级绩效指标分值`，步骤 MUST 成功
- **AND** 步骤结果 MUST 包含 `table`、`headers` 和 `absent`

#### Scenario: 发现不应存在的列时失败
- **WHEN** DSL 文档执行 `table.assert_columns`，且 `target.absent` 中任一列出现在目标表格实际表头中
- **THEN** 步骤 MUST 失败
- **THEN** 错误信息 MUST 标识不应存在的列名
- **AND** 错误诊断 MUST 包含目标表格实际采集到的 `headers`

#### Scenario: 断言指定表格存在目标列
- **WHEN** DSL 文档执行 `table.assert_columns`，且 `target.present` 包含一个或多个列名
- **THEN** runtime MUST 采集目标表格实际 DOM 表头
- **THEN** 如果实际表头包含 `target.present` 中全部列，步骤 MUST 成功
- **AND** 步骤结果 MUST 包含 `present` 和实际 `headers`

#### Scenario: 缺少必需列时失败
- **WHEN** DSL 文档执行 `table.assert_columns`，且 `target.present` 中任一列未出现在目标表格实际表头中
- **THEN** 步骤 MUST 失败
- **THEN** 错误信息 MUST 标识缺失列名
- **AND** 错误诊断 MUST 包含目标表格实际采集到的 `headers`

#### Scenario: 同时断言存在列和不存在列
- **WHEN** DSL 文档执行 `table.assert_columns`，且 `target.present` 和 `target.absent` 均非空
- **THEN** 系统 MUST 在同一次表头采集结果上同时校验存在列和不存在列
- **THEN** 只有全部 `present` 列存在且全部 `absent` 列不存在时，步骤 MUST 成功

### Requirement: 表格列断言作用域
系统 SHALL 将 `table.assert_columns` 的表头采集限定在目标表格作用域内。

#### Scenario: 指定表格名称限定作用域
- **WHEN** DSL 文档执行 `table.assert_columns`，且 `target.table` 为当前模板中的可见表格标题
- **THEN** executor MUST 使用现有表格作用域规则解析匹配表格
- **THEN** runtime MUST 只在该表格作用域和与其关联的 header 容器中采集表头
- **THEN** runtime MUST NOT 使用全页面裸表头扫描结果作为通过依据

#### Scenario: 单个可见表格可省略表格名称
- **WHEN** DSL 文档执行 `table.assert_columns`，且未填写 `target.table`，当前页面只有一张可见主表格
- **THEN** executor MUST 将唯一可见主表格解析为断言作用域
- **THEN** runtime MUST 在该表格作用域内采集表头

#### Scenario: 多张可见表格时拒绝歧义断言
- **WHEN** DSL 文档执行 `table.assert_columns`，且未填写 `target.table`，当前页面存在多张可见主表格
- **THEN** 步骤 MUST 在采集表头前失败
- **THEN** 错误信息 MUST 说明当前页面包含多张表格，并要求补充 `target.table`

#### Scenario: 表格名称不匹配时失败
- **WHEN** DSL 文档执行 `table.assert_columns`，且 `target.table` 不是当前模板中的可见表格标题
- **THEN** 步骤 MUST 在采集表头前失败
- **THEN** 错误信息 MUST 包含 `target.table` 和当前模板可用表格标题

### Requirement: 表头采集与列名匹配
系统 SHALL 使用真实 DOM 表头采集和精确归一化列名匹配执行 `table.assert_columns`。

#### Scenario: 横向滚动表格采集视口外列
- **WHEN** 目标表格存在横向滚动，部分表头列初始不在当前视口内
- **THEN** runtime MUST 通过横向滚动或等效方式采集所有可到达表头
- **THEN** `present` 和 `absent` 校验 MUST 基于采集后的完整去重表头集合执行

#### Scenario: 忽略表头前置必填标识
- **WHEN** 目标表格实际表头为 `* 一级绩效指标`、`＊ 二级绩效指标` 或带其他支持的前置必填标识
- **THEN** 列名匹配 MUST 去除前置必填标识和多余空白
- **THEN** `present: [一级绩效指标, 二级绩效指标]` MUST 能匹配这些表头

#### Scenario: 前缀相似列名不得互相匹配
- **WHEN** 目标表格实际表头包含 `一级绩效指标`
- **THEN** 系统 MUST NOT 将其视为匹配 `一级绩效指标分值`
- **AND** 系统 MUST NOT 将 `一级绩效指标分值` 视为匹配 `一级绩效指标`

#### Scenario: 无法采集任何表头时失败
- **WHEN** DSL 文档执行 `table.assert_columns`，且 runtime 在目标表格作用域内无法采集任何表头
- **THEN** 步骤 MUST 失败
- **THEN** 错误信息 MUST 标识无法采集表格表头
- **AND** 错误诊断 MUST 包含表格作用域解析信息

### Requirement: 表格列断言 DSL 校验
系统 SHALL 在业务执行前校验 `table.assert_columns` target 的结构。

#### Scenario: 接受不存在列断言
- **WHEN** DSL 文档包含 `table.assert_columns`，且 `target.absent` 是非空字符串列表
- **THEN** DSL validation MUST 接受该步骤

#### Scenario: 接受存在列断言
- **WHEN** DSL 文档包含 `table.assert_columns`，且 `target.present` 是非空字符串列表
- **THEN** DSL validation MUST 接受该步骤

#### Scenario: 拒绝空断言目标
- **WHEN** DSL 文档包含 `table.assert_columns`，但未填写 `target.present` 和 `target.absent`
- **THEN** DSL validation MUST 失败
- **THEN** 错误信息 MUST 说明缺少 `target.present` 或 `target.absent`

#### Scenario: 拒绝错误列表格式
- **WHEN** DSL 文档包含 `table.assert_columns`，且 `target.present` 或 `target.absent` 不是非空列表
- **THEN** DSL validation MUST 失败
- **THEN** 错误信息 MUST 指出对应 target 字段格式不正确
