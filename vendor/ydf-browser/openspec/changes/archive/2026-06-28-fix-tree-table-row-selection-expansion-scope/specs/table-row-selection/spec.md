## ADDED Requirements

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
