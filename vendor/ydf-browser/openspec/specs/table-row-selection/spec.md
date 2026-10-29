# table-row-selection Specification

## Purpose
描述 `table_row_selection.select` 的表格行选择语义，包括按行定位勾选数据行、在多表格页面限定表格作用域，以及通过 `target.select_all: true` 点击表头 checkbox 触发表格组件原生全选行为。
## Requirements
### Requirement: 表格行选择全选目标
系统 SHALL 允许 `table_row_selection.select` 通过设置 `target.select_all: true` 点击表格组件表头 checkbox，以选择该表格组件原生暴露的全部行。

#### Scenario: 单个可见表格中选择全部行
- **WHEN** 测试集执行 `table_row_selection.select`，且 `target.select_all` 为 `true`，当前页面只有一张可见主表格
- **THEN** executor MUST 将这张表格解析为选择作用域
- **THEN** runtime MUST 在表头 checkbox 尚未完全选中时点击该 checkbox
- **THEN** 步骤结果 MUST 包含 `select_all: true`

#### Scenario: 指定表格中选择全部行
- **WHEN** 测试集执行 `table_row_selection.select`，且 `target.table` 为一张可见主表格名称、`target.select_all` 为 `true`
- **THEN** executor MUST 使用现有表格作用域规则解析匹配表格的 `fieldid`
- **THEN** runtime MUST 将表头 checkbox 查找和点击限定在该表格作用域内
- **THEN** 步骤结果 MUST 包含 `select_all: true`、`table`，并在可用时包含解析出的 `table_fieldid`

#### Scenario: 多张可见表格时拒绝歧义全选
- **WHEN** 测试集执行 `table_row_selection.select`，且 `target.select_all` 为 `true`、未填写 `target.table`，当前页面存在多张可见主表格
- **THEN** 步骤 MUST 在点击任何 checkbox 前失败
- **THEN** 错误信息 MUST 说明当前页面包含多张表格，并要求补充 `target.table`

### Requirement: 表头 Checkbox 定位
系统 SHALL 在执行 `target.select_all` 时只定位已解析表格的表头 checkbox。

#### Scenario: 忽略数据行 Checkbox
- **WHEN** 已解析表格的表头行和数据行都包含 checkbox 控件
- **THEN** runtime MUST 点击表头区域内的 checkbox 控件
- **THEN** runtime MUST NOT 将 `tbody` 数据行 checkbox 作为全选目标

#### Scenario: 表头 Checkbox 不可用时失败
- **WHEN** 测试集执行 `table_row_selection.select`，且 `target.select_all` 为 `true`，已解析表格有可选择数据行但没有可见表头 checkbox
- **THEN** 步骤 MUST 失败
- **THEN** 错误信息 MUST 标识未找到表头全选 checkbox

#### Scenario: 已选中表头 Checkbox 保持选中
- **WHEN** 已解析表格的表头 checkbox 已处于完全选中状态
- **THEN** runtime MUST 将本次全选操作视为成功
- **THEN** runtime MUST NOT 以会导致全部行反选的方式点击 checkbox

#### Scenario: 点击半选或未选中的表头 Checkbox
- **WHEN** 已解析表格的表头 checkbox 处于未选中或半选状态
- **THEN** runtime MUST 点击表头 checkbox 或其可点击 wrapper
- **THEN** runtime MUST 等待表格选择状态稳定后再返回成功

### Requirement: 全选 DSL 校验
系统 SHALL 将 `target.select_all` 校验为互斥的表格行选择定位方式。

#### Scenario: 接受全选目标
- **WHEN** DSL 文档包含 `table_row_selection.select`，且 `target.select_all` 为 `true`
- **THEN** DSL validation MUST 接受该步骤，且不要求填写 `target.match`、`target.rows`、`target.row_number` 或 `target.first_available`

#### Scenario: 拒绝全选与行定位混用
- **WHEN** DSL 文档包含 `table_row_selection.select`，且 `target.select_all` 为 `true`，同时还包含 `target.match`、`target.rows`、`target.row_number`、`target.row_numbers`、`target.row_index`、`target.first_available` 或 `target.select_first_available` 中任一字段
- **THEN** DSL validation MUST 在业务步骤执行前失败
- **THEN** 错误信息 MUST 说明 `target.select_all` 不能与行定位目标混用

### Requirement: 嵌套 WUI 表格行选择
系统 SHALL 在指定表格作用域后，支持 YonDiF 嵌套 WUI 表格的业务行选择，即使该表格的 header 和 body 分离渲染。

#### Scenario: 指定内部检查小组后选择成员行
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.table` 为 `内部检查小组`
- **AND** `target.match.column` 为 `人员名称`、`target.match.equals` 为 `财会监督1`
- **AND** 页面中 `内部检查小组` 表格 body 存在包含 `财会监督1` 的可选择数据行
- **THEN** executor MUST 将 `target.table` 解析为该子表作用域，并在可用时传递 `table_fieldid`
- **THEN** runtime MUST 将 header 与对应 body 关联为同一目标表格
- **THEN** runtime MUST 在该表格 body 中勾选目标行 checkbox
- **AND** runtime MUST NOT 在其它表格或全页面裸文本范围内选择同名行

#### Scenario: Header root 不含 body 时仍能选择行
- **WHEN** 目标 WUI 表格的 `.wui-table-header` 和 `.wui-table-body` 是分离 DOM 容器
- **AND** fieldid 或表名首先命中 header 相关容器
- **THEN** runtime MUST 通过目标 fieldid、表头集合、几何位置或共同祖先找到对应 body 容器
- **THEN** runtime MUST 在对应 body 容器中执行行匹配和 checkbox 点击

#### Scenario: 目标行存在但无法选择时提供作用域诊断
- **WHEN** `table_row_selection.select` 在指定表格作用域内无法勾选目标行
- **THEN** 错误诊断 MUST 包含目标 `table`、可用时的 `table_fieldid`、目标列、匹配值、解析到的表格根摘要和可见行摘要
- **AND** 错误诊断 MUST 能区分目标表格无数据、列名不匹配和表格 root 不含 body 的情况

### Requirement: 按列值选择表格行
系统 SHALL 在 `table_row_selection.select` 使用 `target.match.column` 和 `target.match.equals` 时，按指定表格列的单元格值定位业务行，并在该行上执行行选择。

#### Scenario: 文本布尔列值可定位业务行
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.match.column` 为 `政府采购标识`
- **AND** `target.match.equals` 为 `是`
- **AND** 目标表格中存在一行的 `政府采购标识` 单元格显示文本为 `是`
- **THEN** runtime MUST 将该单元格值作为匹配依据定位业务行
- **AND** runtime MUST 点击同一业务行的行选择 checkbox、等效行选择控件，或在无选择控件时点击真实可接收 pointer 事件的业务行单元格并带出行点击诊断
- **AND** runtime MUST NOT 将 `政府采购标识` 这一文本单元格本身当作 checkbox

#### Scenario: 单值匹配不得退化为整行文本误选
- **WHEN** `table_row_selection.select` 的 `target.match.column` 为 `政府采购标识`
- **AND** `target.match.equals` 为 `是`
- **AND** 第一条可见数据行整行文本包含 `是`，但其 `政府采购标识` 单元格不是 `是`
- **THEN** runtime MUST NOT 选择该行
- **THEN** runtime MUST 继续查找 `政府采购标识` 单元格等于 `是` 的数据行

#### Scenario: 目标行存在但选择控件缺失时点击并验证业务行
- **WHEN** runtime 已按 `target.match.column` 和 `target.match.equals` 找到目标业务行
- **AND** 该行没有可点击的行选择 checkbox 或等效行选择控件
- **AND** 该行位于已解析的目标表格作用域内
- **THEN** runtime MUST 点击该目标业务行中真实可接收 pointer 事件的单元格以触发表格原生选中/高亮
- **AND** runtime SHOULD 在点击后确认目标行或等效当前行 DOM 出现真实选中证据；页面未暴露可读选中证据时 MUST 记录 `accepted_unconfirmed=true`
- **AND** runtime MUST NOT 退回全页面裸文本点击

### Requirement: 表格行选择的列归属作用域
系统 SHALL 在 `table_row_selection.select` 未显式指定 `target.table` 时，使用目标匹配列的表格归属限定选择作用域；无法唯一确定时必须在点击前失败。

#### Scenario: 目标列唯一归属于可用指标表
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** 未填写 `target.table`
- **AND** `target.match.column` 为 `政府采购标识`
- **AND** 当前模板中只有 `可用指标` 表包含 `政府采购标识` 列
- **THEN** executor MUST 将 `可用指标` 解析为本次行选择作用域
- **AND** executor MUST 在可用时向 runtime 传递该表的 `table_fieldid` 和列清单

#### Scenario: 多张表都包含目标列时拒绝歧义
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** 未填写 `target.table`
- **AND** 当前模板中多张可见主表都包含 `target.match.column`
- **THEN** 步骤 MUST 在点击任何行选择控件前失败
- **THEN** 错误信息 MUST 要求补充 `target.table`

#### Scenario: 目标行存在但点击后未选中时诊断清晰
- **WHEN** runtime 已按 `target.match.column` 和 `target.match.equals` 找到目标业务行
- **AND** 该行没有可点击的行选择 checkbox 或等效行选择控件
- **AND** runtime 点击该业务行后没有检测到真实选中/当前行证据
- **THEN** 步骤 MUST 失败
- **THEN** 错误信息 MUST 包含目标表格、目标列、匹配值，并说明未找到可选择的表格行或已点击业务行但未确认表格行选中

### Requirement: WUI 表格列身份映射
系统 SHALL 在 `table_row_selection.select` 使用 `target.match.column` 和 `target.match.equals` 时，支持 WUI 表格中模板表头身份与运行时行单元格身份不完全相同但语义一致的列值匹配。

#### Scenario: 表头 fieldid 与行单元格 data-index 对齐
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.match.column` 为 `政府采购标识`
- **AND** `target.match.equals` 为 `否`
- **AND** 目标表格表头 `政府采购标识` 的 DOM identity 为 `kyzb_table_isGovPurName`
- **AND** 同一业务行的目标单元格 DOM identity 为 `isGovPurName`
- **AND** 该单元格显示文本为 `否`
- **THEN** runtime MUST 将 `kyzb_table_isGovPurName` 与 `isGovPurName` 识别为同一模板列
- **AND** runtime MUST 使用该单元格值定位业务行
- **AND** runtime MUST 点击同一业务行的行选择 checkbox 或等效行选择控件
- **AND** runtime MUST NOT 因 WUI 单元格内部 wrapper 造成的可见 cell 索引偏移而漏选目标行

### Requirement: 折叠树形表格行选择
系统 SHALL 在 `table_row_selection.select` 的目标业务行位于折叠树形表格子节点时，在已解析的目标表格内逐级展开节点并选择完整匹配的业务行。

#### Scenario: 在指定树形表格内展开并选择目标行
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.table` 或解析出的 `table_fieldid` 唯一指向一张树形表格
- **AND** 目标业务行真实存在但尚未因父节点折叠而进入当前 DOM
- **THEN** runtime MUST 将折叠节点查找、点击、DOM 重查、纵向滚动和目标行判断限定在该目标表格内
- **THEN** runtime MUST 在目标行出现后按既有行匹配语义点击同一行的选择控件

#### Scenario: 不展开其它表格的同类节点
- **WHEN** 当前页面存在多张表格且其它表格也包含可见折叠节点
- **AND** `table_row_selection.select` 已解析出唯一目标表格
- **THEN** runtime MUST NOT 点击目标表格之外的折叠节点
- **AND** runtime MUST NOT 使用其它表格的行变化或滚动状态判断目标遍历进度

#### Scenario: 复合条件换序保持相同选择结果
- **WHEN** `target.match.conditions` 包含多个使用 `equals` 的 AND 条件
- **AND** 任一条件值带前导数字但该值不代表树祖先路径
- **THEN** runtime MUST 使用全部条件匹配最终业务行
- **AND** runtime MUST NOT 因条件数组顺序不同而改变折叠节点遍历范围或最终选择结果

#### Scenario: 单目标编码继续使用安全前缀优化
- **WHEN** 行定位只有一个目标文本且该文本具有可识别的前导层级编码
- **AND** 可见折叠父节点编码是目标编码的真前缀
- **THEN** runtime MAY 优先展开相关父节点
- **AND** runtime MUST 在无法确认相关父节点时回退到目标表格内的通用遍历

### Requirement: 树形表格行选择诊断
系统 SHALL 为触发树形表格遍历的 `table_row_selection.select` 记录可审计的查找诊断。

#### Scenario: 展开后成功选择时记录诊断
- **WHEN** runtime 展开至少一个折叠节点后成功选择目标行
- **THEN** 步骤结果 MUST 在 `data.row_search` 中记录目标表格、匹配条件、`expanded`、`scrolled`、`found` 和 `elapsed_ms`
- **AND** `found` MUST 为 `true`

#### Scenario: 遍历完成仍未找到目标行时记录诊断
- **WHEN** runtime 在目标表格内完成允许的展开和滚动后仍未找到完整匹配行
- **THEN** 步骤 MUST 失败并保留目标表格、匹配条件、`expanded`、`scrolled`、`found` 和 `elapsed_ms` 诊断
- **AND** 错误信息 MUST 能区分“未找到匹配行”与“已找到业务行但缺少选择控件”

### Requirement: first_available 选择无 checkbox 的首条有效业务行
系统 SHALL 将 `table_row_selection.select target.first_available` 解释为选择目标表格内第一条有效业务行；当该行没有 checkbox 或等效行选择控件时，runtime MUST 在已解析表格作用域内点击该业务行，并在确认真实选中/当前行证据后返回成功。

#### Scenario: 目标表首条业务行没有 checkbox 时点击并验证行
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.table` 唯一指向一张可见主表格
- **AND** `target.first_available` 为 `true`
- **AND** 该表格第一条有效业务行没有可见 checkbox 或等效行选择控件
- **THEN** runtime MUST 点击该业务行
- **AND** runtime SHOULD 在点击后确认目标行或等效当前行 DOM 出现真实选中证据；页面未暴露可读选中证据时 MUST 记录 `accepted_unconfirmed=true`
- **AND** runtime MUST NOT 退回全页面裸文本点击
- **AND** 步骤结果 MUST 包含 `row_numbers: [1]`、`table`，并在可用时包含 `table_fieldid`

#### Scenario: 首条业务行存在 checkbox 时仍优先点击 checkbox
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.first_available` 为 `true`
- **AND** 第一条有效业务行包含可见 checkbox 或等效行选择控件
- **THEN** runtime MUST 优先点击该选择控件
- **AND** runtime MUST NOT 因新增行点击兜底而跳过选择控件

#### Scenario: first_available 忽略非业务行
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.first_available` 为 `true`
- **AND** 目标表格包含表头、`暂无数据` 占位行、小计行或合计行
- **THEN** runtime MUST NOT 将这些非业务行作为 first available 候选
- **AND** runtime MUST 继续查找第一条有效业务行

#### Scenario: 没有有效业务行时 first_available 失败
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.first_available` 为 `true`
- **AND** 已解析目标表格没有任何有效业务行
- **THEN** 步骤 MUST 失败
- **AND** 错误信息 MUST 说明未找到可选择的表格行号或未找到有效业务行，并包含目标表格诊断

#### Scenario: first_available 遵守多表格歧义规则
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.first_available` 为 `true`
- **AND** 未填写 `target.table`
- **AND** 当前页面存在多张可见主表格且无法唯一确定目标表格
- **THEN** 步骤 MUST 在点击任何行或选择控件前失败
- **AND** 错误信息 MUST 要求补充 `target.table`

### Requirement: 按行号选择无 checkbox 行必须点击真实可接收事件的业务行
系统 SHALL 在 `table_row_selection.select` 使用 `target.row_number` 或 `target.first_available` 定位无 checkbox 业务行时，点击目标表格内真实可接收 pointer 事件的业务行区域；优先确认目标行进入真实选中/当前行状态，页面未暴露可读选中态时必须带出未确认但已点击真实业务行的诊断。

#### Scenario: 调出方无 checkbox 行点击后确认选中
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.table` 为 `调出方`
- **AND** `target.row_number` 为 `1`
- **AND** 目标表格第一条有效业务行没有可见 checkbox 或等效行选择控件
- **THEN** runtime MUST 在已解析的 `调出方` 表格作用域内点击可接收 pointer 事件的业务行单元格
- **AND** runtime MUST NOT 点击被表单、旧 DOM 或其它层覆盖的同文本行
- **AND** runtime SHOULD 在点击后确认目标行或等效当前行 DOM 出现真实选中证据
- **AND** 当页面未暴露可读选中证据但点击目标是真实可接收事件的业务行单元格时，步骤结果 MUST 包含 `accepted_unconfirmed=true`
- **AND** 步骤结果 MUST 包含 `row_numbers: [1]`、`table`、可用时的 `table_fieldid`，以及行点击诊断

#### Scenario: 行点击无法命中真实可接收业务行时失败
- **WHEN** runtime 已按行号找到目标业务行
- **AND** 该行没有可点击的行选择 checkbox 或等效行选择控件
- **AND** 该行或其对齐业务单元格无法通过 `elementFromPoint` 确认可接收 pointer 事件
- **THEN** `table_row_selection.select` MUST 失败
- **AND** 错误信息 MUST 说明未找到可选择的表格行
- **AND** 错误诊断 MUST 包含目标 `table`、可用时的 `table_fieldid`、行号和表格根摘要

#### Scenario: fieldid 命中无可选业务行时不得按表名回退
- **WHEN** `target.table` 为 `调出方`
- **AND** executor 已将 `target.table` 解析为 `table_fieldid`
- **AND** runtime 已根据 `table_fieldid` 找到表格根
- **AND** 该表格根内不存在可接收 pointer 事件的有效业务行
- **THEN** `table_row_selection.select` MUST 在点击其它表格前失败
- **AND** runtime MUST NOT 按 `target.table` 的可见标题重新解析其它表格根
- **AND** 错误诊断 MUST 包含目标 `table`、`table_fieldid` 和已命中的表格根摘要
- **AND** runtime MUST 继续支持同一 `table_fieldid` 表格内 WUI 表头和表体分裂 DOM 的聚合

### Requirement: 表格行选择实际表格根诊断
系统 SHALL 在 `table_row_selection.select` 成功后记录 runtime 实际命中的表格根摘要，使报告能区分 DSL 声明目标和真实 DOM 点击作用域。

#### Scenario: 成功选择时记录实际根身份
- **WHEN** `table_row_selection.select` 成功选中一行
- **AND** runtime 已解析出表格根
- **THEN** 步骤结果 MUST 包含实际表格根诊断
- **AND** 诊断 MUST 在可用时包含 root `fieldid`、`source` 和 `selectableRows`
- **AND** 诊断 MUST NOT 只复述 DSL 中的 `target.table`

#### Scenario: 未暴露根身份时仍保留选择诊断
- **WHEN** `table_row_selection.select` 成功选中一行
- **AND** runtime 无法从 DOM 根读取 root `fieldid`
- **THEN** 步骤结果 MUST 保留已有选择诊断
- **AND** 诊断 MUST 在可用时包含 root `source`、`rows` 或 `selectableRows`

### Requirement: 复合条件行选择必须完整匹配同一业务行
系统 SHALL 在 `table_row_selection.select` 使用 `target.match.conditions` 时，将每个条件绑定到其声明列，并只选择同一业务行内满足全部条件的行。

#### Scenario: 首条件重复时选择完整匹配行
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.table` 为 `table1`
- **AND** `target.match.conditions` 包含 `一级项目名称=财政一级项目ys06231632` 和 `指标金额=888.00`
- **AND** 第一条可见数据行只满足 `一级项目名称=财政一级项目ys06231632`
- **AND** 第四条可见数据行同时满足 `一级项目名称=财政一级项目ys06231632` 和 `指标金额=888.00`
- **THEN** runtime MUST 点击第四条业务行的行选择 checkbox 或等效行选择控件
- **AND** runtime MUST NOT 选择第一条只满足部分条件的业务行

#### Scenario: 复合条件按声明列匹配而非整行包含
- **WHEN** `target.match.conditions` 包含多个列条件
- **AND** 某条数据行的整行文本包含所有条件值，但至少一个条件值位于错误列
- **THEN** runtime MUST NOT 将该行视为完整匹配行
- **AND** runtime MUST 继续查找每个条件值都位于声明列中的业务行

#### Scenario: 复合条件顺序不影响选择结果
- **WHEN** 两次 `table_row_selection.select` 使用相同的 `target.match.conditions` 集合但条件顺序不同
- **AND** 当前表格中存在唯一完整匹配业务行
- **THEN** runtime MUST 在两次执行中选择同一业务行

### Requirement: fieldid 表格根候选必须优先前景业务行
系统 SHALL 在 `table_row_selection.select` 已通过当前 manifest 将 `target.table` 解析为 `table_fieldid` 时，只在该 `table_fieldid` 对应的 DOM 候选内选择表格根，并优先选择当前前景、可见、包含可接收 pointer 事件业务行的候选根。

#### Scenario: 同 fieldid 背景旧根有 checkbox 时仍选择前景业务行根
- **WHEN** 测试集执行 `table_row_selection.select`
- **AND** `target.table` 为 `调出方`
- **AND** 当前 manifest 将 `调出方` 解析为 `table_fieldid=table1`
- **AND** 页面 DOM 中同时存在多个 `table1_drag` 或 `table1` 候选根
- **AND** 背景旧候选根包含 `selectableRows` 但没有可接收 pointer 事件的有效业务行
- **AND** 前景候选根没有可见 checkbox，但第一条业务行存在可接收 pointer 事件的业务单元格
- **THEN** runtime MUST 选择前景候选根作为 `table_row_selection.select` 的实际表格根
- **AND** runtime MUST 点击前景候选根内第一条业务行的可接收业务单元格
- **AND** runtime MUST NOT 因背景旧候选根的 `selectableRows` 较高而选择背景旧根

#### Scenario: fieldid 已解析时不得按表名文本回退
- **WHEN** executor 已将 `target.table` 解析为 `table_fieldid`
- **AND** runtime 在该 `table_fieldid` 的 DOM 候选中找不到任何可接收 pointer 事件的有效业务行
- **THEN** `table_row_selection.select` MUST 在点击其它表格前失败
- **AND** runtime MUST NOT 按 `target.table` 的可见标题或文本重新全局匹配其它表格根
- **AND** 错误诊断 MUST 包含目标 `table`、`table_fieldid` 和已命中的 fieldid 候选根摘要

#### Scenario: 保持 WUI 表头表体分裂聚合
- **WHEN** `table_fieldid` 对应的 WUI 表格表头和表体位于分裂 DOM 结构中
- **AND** 表头候选和表体候选需要聚合后才能表示完整表格根
- **THEN** runtime MUST 继续聚合该 fieldid 内的表头和表体候选
- **AND** 前景业务行优先级 MUST 基于聚合后的表格根计算
- **AND** runtime MUST NOT 为了前景判断破坏既有列匹配、checkbox 优先或无 checkbox 行点击兜底行为

### Requirement: 表格行选择消费统一表格作用域
系统 MUST 在执行 `table_row_selection.select` 前通过统一表格作用域能力解析目标表格和匹配条件引用列。runtime MUST 只在解析结果限定的表格内执行行匹配、树形展开、checkbox 选择或业务行点击。

#### Scenario: 复合条件列在选择前完成预校验
- **WHEN** `target.match.conditions` 引用多个列
- **THEN** 系统 MUST 在扫描业务行前确认全部列属于同一已解析表格
- **AND** 任一列缺失时步骤 MUST 失败且不得点击页面

#### Scenario: runtime 不按旧参数回退其它表格
- **WHEN** 已解析表格作用域的运行时根内不存在目标业务行
- **THEN** 当前步骤 MUST 按目标表格无匹配行失败
- **AND** runtime MUST NOT 使用原始 `target.table`、可见标题或全页面文本另行解析其它表格
