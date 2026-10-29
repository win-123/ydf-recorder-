# table-column-assertions Specification

## Purpose

Defines DSL and runtime behavior for asserting table header column presence or absence in YonDiF pages.
## Requirements
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

### Requirement: 表格列值断言使用目标表格作用域
系统 SHALL 在执行 `table.assert_column_values` 时将列值采集限定在目标表格作用域内，并使用目标表格的真实表头定位列。

#### Scenario: 指定表格后采集该表格列值
- **WHEN** DSL 文档执行 `table.assert_column_values`，且 `target.table` 指向当前模板中的目标表格
- **THEN** executor MUST 将 `target.table` 解析为目标表格作用域
- **THEN** runtime MUST 只在该表格作用域内采集 `target.column` 的单元格值
- **AND** runtime MUST NOT 使用全页面其它表格或表单区域中的同名/近似列作为采集来源

#### Scenario: 未指定表格时按目标列推断唯一表格
- **WHEN** DSL 文档执行 `table.assert_column_values`，未填写 `target.table`
- **AND** 当前模板只有一个可见主表格包含 `target.column`
- **THEN** executor MUST 将该表格作为目标表格作用域
- **THEN** runtime MUST 在该表格作用域内采集列值

#### Scenario: 多表格无法唯一推断时失败
- **WHEN** DSL 文档执行 `table.assert_column_values`，未填写 `target.table`
- **AND** 当前页面存在多张可见主表格，且无法根据 `target.column` 唯一确定目标表格
- **THEN** 步骤 MUST 在采集单元格值前失败
- **AND** 错误信息 MUST 要求补充 `target.table` 或更明确的目标上下文

### Requirement: 表格行值断言按业务行和列身份读取字段
系统 SHALL 在执行 `table.assert_row_values` 时先在目标表格内定位业务行，再按同一表格的列身份读取该行字段值。

#### Scenario: 按匹配列定位行并读取目标列
- **WHEN** DSL 文档执行 `table.assert_row_values`
- **AND** `target.match.column` 为 `被授权人名称`、`target.match.equals` 为 `人员二十二`
- **AND** `target.fields` 包含 `可授权金额: "400.00"`
- **THEN** runtime MUST 在目标表格内找到 `被授权人名称 = 人员二十二` 的业务行
- **THEN** runtime MUST 从该业务行的 `可授权金额` 列读取实际值
- **AND** 只有该实际值匹配 `400.00` 时步骤 MUST 成功

#### Scenario: 多条件匹配使用列值而不是整行裸文本
- **WHEN** DSL 文档执行 `table.assert_row_values`，且 `target.match.conditions` 包含多个列条件
- **THEN** runtime MUST 按每个条件的列名读取候选行对应列值
- **AND** runtime MUST 只在所有条件列值均匹配时选择该业务行

#### Scenario: 目标行存在但字段列缺失时失败
- **WHEN** DSL 文档执行 `table.assert_row_values`
- **AND** runtime 已找到匹配业务行
- **AND** 目标表格表头不包含 `target.fields` 中的任一字段列
- **THEN** 步骤 MUST 失败
- **AND** 错误信息 MUST 标识缺失字段列和当前目标表格 headers

### Requirement: 表格数据值断言使用稳定列映射
系统 SHALL 使用稳定列映射读取 `table.assert_column_values` 和 `table.assert_row_values` 的单元格值，避免相邻列、固定列副本或其它表格串列。

#### Scenario: 相邻列不得串读
- **WHEN** 目标表格同时包含 `可授权金额`、`起始时间`、`项目名称` 等相邻列
- **THEN** 断言 `可授权金额` 时 runtime MUST 读取 `可授权金额` 列的单元格
- **AND** runtime MUST NOT 将 `起始时间`、`项目名称` 或其它相邻列的值作为 `可授权金额` 的实际值

#### Scenario: header 和 body 分离渲染仍能对齐
- **WHEN** YonDiF 表格将 header 和 body 分离渲染，或存在固定列副本
- **THEN** runtime MUST 优先使用列 identity、表头 identity、dataField、fieldid 或等效 DOM 属性对齐 header 和 body 单元格
- **AND** 只有缺少 identity 时才能在目标表格范围内使用列索引或几何对齐兜底

#### Scenario: 失败诊断包含表格和值采集上下文
- **WHEN** 数据值断言因列缺失、行缺失、值不匹配或无法唯一确定表格而失败
- **THEN** 错误诊断 MUST 包含可用时的 `table`、`table_fieldid`、目标列、匹配条件和目标表格 headers
- **AND** 错误诊断 MUST NOT 只返回其它列的误采值作为失败依据

### Requirement: 表格数据值断言 DSL 支持可选表格作用域
系统 SHALL 允许 `table.assert_column_values` 和 `table.assert_row_values` 在 target 中使用可选表格作用域字段，以便多表格页面明确断言目标。

#### Scenario: 接受列值断言的表格作用域字段
- **WHEN** DSL 文档包含 `table.assert_column_values`，且 target 中包含 `table` 或 `table_name`
- **THEN** DSL validation MUST 接受该步骤
- **AND** executor MUST 将该字段用于目标表格作用域解析

#### Scenario: 接受行值断言的表格作用域字段
- **WHEN** DSL 文档包含 `table.assert_row_values`，且 target 中包含 `table` 或 `table_name`
- **THEN** DSL validation MUST 接受该步骤
- **AND** executor MUST 将该字段用于目标表格作用域解析

#### Scenario: 显式表格作用域可使用运行时 fieldid
- **WHEN** DSL 文档包含 `table.assert_row_values` 或 `table.assert_column_values`
- **AND** `target.table` 填写的是当前 DOM 中可见表格的 fieldid
- **AND** 当前动态模板 manifest 未包含该 fieldid
- **THEN** executor MUST NOT 在采集前报表格名称未匹配
- **AND** runtime MUST 使用该 fieldid 限定目标表格作用域

### Requirement: 嵌套 WUI 表格数据值断言
系统 SHALL 在表格数据值断言中正确处理 YonDiF 嵌套 WUI 表格的 header/body 分离渲染，并将读取限定在目标表格作用域内。

#### Scenario: 指定内部检查小组后读取成员列值
- **WHEN** DSL 文档执行 `table.assert_column_values`
- **AND** `target.table` 为 `内部检查小组`
- **AND** `target.column` 为 `人员名称`
- **AND** 页面中 `内部检查小组` 表格 body 存在 `财会监督1` 成员行
- **THEN** executor MUST 将 `target.table` 解析为目标表格作用域，并在可用时传递 `table_fieldid`
- **THEN** runtime MUST 将目标表头与对应 body 单元格关联
- **THEN** runtime MUST 返回 `人员名称` 列中的 `财会监督1`
- **AND** runtime MUST NOT 因 header root 不包含 body 而返回空值

#### Scenario: 行值断言复用同一表格簇映射
- **WHEN** DSL 文档执行 `table.assert_row_values`
- **AND** `target.table` 指向 header/body 分离的嵌套 WUI 表格
- **AND** `target.match` 能在对应 body 中匹配业务行
- **THEN** runtime MUST 在同一目标表格簇中定位业务行
- **THEN** runtime MUST 使用同一表格簇的列映射读取 `target.fields` 中的字段值
- **AND** runtime MUST NOT 从其它嵌套子表、固定列副本或背景列表表格读取值

#### Scenario: 分离表格读取失败时输出可解释诊断
- **WHEN** `table.assert_column_values` 或 `table.assert_row_values` 在指定表格作用域下无法读取目标值
- **THEN** 错误诊断 MUST 包含目标 `table`、可用时的 `table_fieldid`、目标列、当前目标表格 headers 和可见 row 文本摘要
- **AND** 如果页面全局调试文本中存在目标值但 scoped 读取为空，诊断 MUST 暴露表格 root 与 body 关联信息，方便定位 header/body 分离问题

### Requirement: 表格列值断言忽略汇总行
系统 SHALL 在执行 `table.assert_column_values` 时只采集目标表格的业务数据行，MUST 排除表格页脚、汇总、小计、合计、总计等非业务数据行。

#### Scenario: WUI 小计行不参与列值断言
- **WHEN** DSL 文档执行 `table.assert_column_values`
- **AND** `target.column` 为 `项目名称`
- **AND** 目标表格包含业务行 `项目名称 = ui自动化wdy0033`
- **AND** 目标表格末尾存在 class 包含 `tfoot-tr` 或 `bsubtotal`、行文本为 `小计 190,000.00` 的汇总行
- **THEN** runtime MUST 返回业务行中的 `ui自动化wdy0033`
- **AND** runtime MUST NOT 将汇总行中的 `190,000.00` 纳入 `values`
- **AND** 当所有业务行的 `项目名称` 均匹配 `target.equals` 时步骤 MUST 成功

#### Scenario: 中文汇总文本行不参与列值断言
- **WHEN** 目标表格存在可见行，其整行文本或首个可见单元格以 `小计`、`合计`、`汇总` 或 `总计` 开头
- **THEN** `table.assert_column_values` MUST 将该行视为汇总行并排除
- **AND** 排除逻辑 MUST 在按列 identity、列索引或几何兜底读取目标列之前生效

#### Scenario: 普通业务行仍可正常采集
- **WHEN** 目标表格存在普通业务行，其目标列值等于 `target.equals`
- **AND** 该行 class 不表示 footer、summary、total、subtotal 或 tfoot
- **AND** 该行首个可见单元格不表示 `小计`、`合计`、`汇总` 或 `总计`
- **THEN** `table.assert_column_values` MUST 保留该业务行参与断言
- **AND** 现有表格作用域、header/body 分离和固定列副本对齐能力 MUST 保持可用

### Requirement: 表格定位使用规则推导身份
系统 SHALL 在表格行选择、列值采集、列断言和可编辑表格录入中，使用 `LCDTable` 的 `divCode`、表格运行时 `fieldid`、列 `dataField` 和固定表头/表体身份推导目标表格与列。

#### Scenario: 表格根和表头表体身份可推导
- **WHEN** 模板中表格容器 `divCode=userTable`
- **THEN** executor MUST 可将该表格运行时根身份解析为 `userTable_table`
- **AND** runtime MUST 可在该表格根内使用 `table-header` 和 `table-body` 识别表头、表体和数据行

#### Scenario: 表格列使用 table fieldid and dataField
- **WHEN** 目标表格运行时身份为 `userTable_table`
- **AND** 目标列模板 `dataField=code`
- **THEN** runtime MUST 优先尝试列身份 `userTable_table_code` 或等价 DOM identity 定位表头和单元格
- **AND** 如果身份冲突或缺失，runtime MUST 保留现有表头文本和表格作用域兜底诊断

### Requirement: 表格断言消费统一表格作用域
系统 MUST 在执行 `table.assert_columns`、`table.assert_column_values` 或 `table.assert_row_values` 前解析唯一表格作用域，并将 `present` 列、目标值列、行匹配列和字段列作为动作必需列进行预校验。`absent` 列 SHALL 作为否定断言保留，MUST NOT 被当作必需存在列。

#### Scenario: 列值断言在采集前校验目标列
- **WHEN** `table.assert_column_values` 声明目标列
- **THEN** 系统 MUST 在采集单元格值前确认目标列属于唯一表格作用域
- **AND** 目标列缺失时 MUST 直接报告列预校验失败

#### Scenario: absent 列不参与必需列预校验
- **WHEN** `table.assert_columns` 仅声明 `target.absent`
- **THEN** 系统 MUST 解析唯一表格作用域后采集真实表头
- **AND** 系统 MUST NOT 因 `absent` 中声明的列不存在而在断言前失败
