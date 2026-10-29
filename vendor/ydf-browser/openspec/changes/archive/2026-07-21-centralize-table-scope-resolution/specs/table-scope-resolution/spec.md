## ADDED Requirements

### Requirement: 表格类步骤统一解析表格作用域
系统 SHALL 在主表、可编辑表格和树形表格的表格类 DSL 动作执行前，通过同一表格作用域能力解析目标表格身份、当前前景运行时根、必需列和诊断证据。行匹配、行选择、录入和点击 SHALL 继续由具体动作执行。

#### Scenario: 表格动作在执行前获得唯一作用域
- **WHEN** 表格类 DSL 动作声明表格名称、表格 fieldid 或必需列
- **THEN** 系统 MUST 在产生页面副作用前解析唯一表格作用域
- **AND** 具体动作 MUST 消费该解析结果，MUST NOT 使用原始目标参数另行选择其它表格

#### Scenario: 弹出参照内部候选表格不纳入首期作用域
- **WHEN** 可编辑表格字段打开弹出参照，参照内部包含候选表格
- **THEN** 弹出参照流程 MUST 继续管理其内部候选表格
- **AND** 通用表格作用域能力 MUST NOT 将该候选表格当作单据页表格类动作目标

### Requirement: 显式表格 fieldid 是硬约束
系统 MUST 将 `target.table` 对表 region fieldid 或 runtime fieldid 的精确匹配视为硬约束。解析出的 fieldid 不存在、不可见、不可交互或不包含动作必需列时，系统 MUST 失败，MUST NOT 回退到同名表格、首个可见表格或全页面文本匹配。

#### Scenario: 显式 runtime fieldid 不可交互时失败
- **WHEN** `target.table` 精确等于目标表格 runtime fieldid
- **AND** 当前前景运行时中该 fieldid 对应表格不存在或不可交互
- **THEN** 步骤 MUST 在动作执行前失败
- **AND** 诊断 MUST 标识请求 fieldid、候选运行时状态和未回退原因

#### Scenario: 显式 fieldid 缺少必需列时失败
- **WHEN** `target.table` 精确匹配一张表格 fieldid
- **AND** 动作引用的任一必需列不属于该表格
- **THEN** 步骤 MUST 在行查找、点击、断言或录入前失败
- **AND** 系统 MUST NOT 改选包含该列的其它表格

### Requirement: 未指定 fieldid 时必须唯一消歧
系统 SHALL 在未提供精确 fieldid 时，使用表格语义名称、manifest 身份、动作必需列和当前前景运行时证据解析候选。只有一个候选满足全部条件时才能成功；评分和候选顺序只能用于诊断排序，MUST NOT 消除歧义。

#### Scenario: 名称和必需列唯一确定表格
- **WHEN** `target.table` 匹配多张模板表格的语义名称
- **AND** 只有一张当前前景可见表格包含动作全部必需列
- **THEN** 系统 MUST 解析到该唯一表格作用域

#### Scenario: 多个候选仍满足条件时失败
- **WHEN** 多张当前前景可见表格同时匹配表格名称和全部必需列
- **THEN** 步骤 MUST 在动作执行前失败
- **AND** 诊断 MUST 列出每个候选的名称、fieldid、前景状态、可见列和冲突原因

### Requirement: 前景运行时证据是最终事实源
系统 MUST 将当前前景弹窗或抽屉作为表格作用域的硬交互上下文，并以真实可见、可交互的运行时 DOM 作为最终事实源。manifest SHALL 提供候选和业务语义；两者冲突时系统 MUST 记录差异，MUST NOT 穿过前景上下文操作背景表格。

#### Scenario: 前景存在时拒绝背景 fieldid
- **WHEN** 当前存在接收交互的前景弹窗或抽屉
- **AND** `target.table` 只匹配背景页面中的表格 fieldid
- **THEN** 步骤 MUST 失败并说明目标存在但当前不可交互
- **AND** 系统 MUST NOT 点击背景表格

#### Scenario: 运行时唯一可见候选覆盖过期 manifest 提示
- **WHEN** manifest 提供多个语义候选
- **AND** 当前前景运行时只有一个候选真实存在、可见且可交互
- **THEN** 系统 MUST 解析到该运行时候选
- **AND** 诊断 SHALL 记录 manifest 候选与运行时候选的差异

### Requirement: 表格作用域按步骤刷新并受控重试
系统 MUST 在每个表格类 DSL 步骤开始时重新解析表格作用域，MUST NOT 跨步骤复用运行时根。动作执行前发现已解析 DOM 根失效且尚未产生页面副作用时，统一解析能力 SHALL 最多重新解析一次；动作执行者 MUST NOT 静默使用旧参数走另一套查表规则。

#### Scenario: 动态模板切换后重新解析
- **WHEN** 前一步导致单据模板、前景上下文或可见列变化
- **THEN** 下一表格类步骤 MUST 从当前 manifest 和运行时 DOM 重新解析作用域

#### Scenario: 执行前 DOM 根失效时只重试一次
- **WHEN** 表格作用域已解析但动作尚未产生页面副作用
- **AND** 执行前校验发现运行时根已失效
- **THEN** 统一解析能力 SHALL 最多重新解析一次
- **AND** 第二次仍不稳定时步骤 MUST 失败

### Requirement: 每次解析都生成表格作用域证据
系统 SHALL 为每次表格作用域解析生成证据。成功步骤 MUST 保留紧凑身份，包括表格名称、fieldid、前景状态和已校验列；失败或调试报告 MUST 展开候选、排除原因、运行时状态和 manifest 差异。

#### Scenario: 成功报告保留紧凑身份
- **WHEN** 表格作用域成功解析且动作完成
- **THEN** 步骤数据 MUST 包含实际表格名称、fieldid、前景状态和动作必需列

#### Scenario: 失败报告保留当次页面证据
- **WHEN** 表格作用域解析失败
- **THEN** 报告 MUST 使用失败当时已采集的候选和排除原因
- **AND** 系统 MUST NOT 依赖失败后重新扫描可能已经变化的页面来生成核心诊断
