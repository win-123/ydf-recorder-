# editable-table-cell-entry Specification

## Purpose
约束可编辑表格按模板列身份定位并录入目标单元格，避免横向滚动、虚拟表格重排或同表相邻字段导致错列写入，并为录入结果提供可追踪诊断。

## Requirements

### Requirement: 可编辑表格单元格按身份定位
系统 SHALL 在执行 `editable_table.fill_row` 时优先使用模板列身份定位目标单元格，包括目标列 `fieldid`、`dataField`、所属表格 `fieldid` 和列组件类型。

#### Scenario: 模板身份阻止计量数写入备注
- **WHEN** DSL 文档执行 `editable_table.fill_row`，目标表格为 `项目测算信息`，字段包含 `计量数: "500"`
- **AND** 当前模板中 `计量数` 映射到 `dataField=estVal`，同一表格中 `备注` 映射到 `dataField=activityDesc`
- **THEN** 系统 MUST 激活并写入 `estVal` 对应的行单元格
- **AND** 系统 MUST NOT 将 `"500"` 写入 `activityDesc` 或 `备注` 对应的单元格

#### Scenario: 横向滚动后保持列身份
- **WHEN** 同一个 `editable_table.fill_row` 步骤连续录入多个字段，前一个字段录入导致表格横向滚动或可见列重排
- **THEN** 系统 MUST 在每个字段录入前重新按目标列身份定位单元格
- **AND** 系统 MUST NOT 复用上一次字段的过期单元格、过期表头或过期列索引

#### Scenario: 文本几何兜底保持可用
- **WHEN** 目标页面 DOM 缺少可用于匹配模板列身份的属性
- **THEN** 系统 SHALL 使用现有表头文本和几何映射作为兜底定位方式
- **AND** 系统 MUST 在调试或步骤数据中标记该字段使用了文本几何兜底

### Requirement: 可编辑表格录入诊断
系统 SHALL 在可编辑表格单元格录入成功或失败时暴露足够的列身份和定位来源信息，用于判断实际写入目标是否与 DSL 字段一致。

#### Scenario: 成功录入报告目标身份
- **WHEN** `editable_table.fill_row` 成功录入某个字段
- **THEN** 步骤结果 SHALL 保留原有 `column` 和 `value`
- **AND** 步骤结果 SHALL 包含该字段的目标列身份信息，例如 `fieldid`、`data_field`、`table_fieldid` 或等价诊断字段

#### Scenario: 身份冲突时失败而不是报告成功
- **WHEN** 运行时定位结果能判断实际命中的单元格身份与目标列身份冲突
- **THEN** 系统 MUST 让当前 `editable_table.fill_row` 步骤失败
- **AND** 错误信息 MUST 包含 DSL 列名、目标列身份、实际命中身份或定位来源

### Requirement: 可编辑表格参照列自动关闭后按回填成功收口
系统 SHALL 在执行 `editable_table.fill_row` 录入可编辑表格弹出参照列时，将目标单元格已回填且参照候选层已关闭识别为字段录入成功。

#### Scenario: 参照自动关闭且页面存在保存按钮
- **WHEN** DSL 文档执行 `editable_table.fill_row`，目标表格为 `汇款转账`，字段 `收款方户名` 使用 `{filter: 严巴天, first_available: true}`
- **AND** 运行时选择参照候选后目标行已回填 `严巴天`、账号或开户行等参照带出值
- **AND** 当前编辑页底部仍存在页面级 `保存` 按钮
- **THEN** 系统 MUST 将 `收款方户名` 字段录入判定为成功
- **AND** 系统 MUST NOT 因页面级 `保存` 按钮存在而继续查找弹出参照确认按钮

#### Scenario: 参照关闭但未回填时失败
- **WHEN** 可编辑表格弹出参照候选层在选择后关闭
- **AND** 目标单元格在等待窗口内没有发生可识别回填
- **THEN** 系统 MUST 让当前 `editable_table.fill_row` 步骤失败
- **AND** 错误信息 MUST 指向参照选择未回填到目标单元格，而不是报告缺少确认按钮

### Requirement: 弹出参照确认范围与背景页面隔离
系统 MUST 只在当前活动弹出参照根内判断确认按钮和参照可见性，背景页面、固定底栏、业务助手和普通编辑页按钮不得影响参照确认状态。

#### Scenario: 背景保存按钮不表示参照仍可见
- **WHEN** 弹出参照候选表格、树、列表或过滤区已经不可见
- **AND** 当前页面其他区域存在可见 `保存`、`确定` 或 `确认` 按钮
- **THEN** 系统 MUST 将当前参照候选层视为已关闭
- **AND** 系统 MUST NOT 点击这些背景按钮作为弹出参照确认动作

#### Scenario: 活动参照内保存仍可确认
- **WHEN** 当前活动弹出参照根仍包含可见候选区和页脚 `保存` 按钮
- **AND** 候选行已经被选择且目标单元格尚未回填
- **THEN** 系统 MUST 允许将该参照根内的 `保存` 作为弹出参照确认动作
- **AND** 系统 MUST 在点击确认后等待目标单元格回填

### Requirement: 可编辑表格结构化参照目标优先进入弹出参照流程
系统 MUST 在执行 `editable_table.fill_row` 时识别字段值中的结构化弹出参照语义，并优先使用弹出参照选择流程录入目标单元格。

#### Scenario: YDFInput 列使用树表参照结构选择物资分类
- **WHEN** DSL 文档执行 `editable_table.fill_row`，目标表格为 `物资入库`
- **AND** 字段 `物资分类` 的模板列组件为 `YDFInput`
- **AND** 字段值包含 `tree.label: A05040101 复印纸` 和 `first_available: true`
- **THEN** 运行时 MUST 将该字段值视为结构化弹出参照目标
- **AND** 运行时 MUST 打开或复用当前可见的物资类别参照弹窗，在该弹窗根内选择 `A05040101 复印纸` 树上下文
- **AND** 如果该弹窗包含右侧候选表格，运行时 MUST 选择当前树上下文下第一条有效右侧候选表格数据行
- **AND** 运行时 MUST 确认参照或等待目标单元格回填
- **AND** 运行时 MUST NOT 将该对象字符串化写入 `物资分类` 单元格
- **AND** 运行时 MUST NOT 仅因 `物资分类` 当前单元格浅层回填而把未选中右侧候选表格数据行的操作判定为成功

#### Scenario: 结构化目标无法打开参照时直接失败
- **WHEN** `editable_table.fill_row` 的某个字段值包含 `tree`、`tab`、`match`、`row_number`、`first_available` 或 `selections` 中任一结构化参照目标
- **AND** 运行时无法为该目标字段打开或解析弹出参照根
- **THEN** 当前 `editable_table.fill_row` 步骤 MUST 在该字段处失败
- **AND** 错误信息 MUST 包含表格名、行号、列名、结构化目标摘要和可见单元格或弹窗诊断
- **AND** 运行时 MUST NOT 回退到普通文本、数字或 choice 录入路径

#### Scenario: 结构化参照选择未回填时失败
- **WHEN** 运行时已按结构化参照目标选择候选并关闭或确认参照弹窗
- **AND** 目标可编辑表格单元格在等待窗口内没有发生可识别回填
- **THEN** 当前字段 MUST 失败
- **AND** 错误信息 MUST 指向弹出参照选择未回填到目标单元格
- **AND** 运行时 MUST NOT 继续录入后续字段并把失败归因到后续列

### Requirement: 可编辑表格结构化参照诊断参与字段结果
系统 SHALL 在 `editable_table.fill_row` 通过结构化弹出参照完成单元格录入时，将参照选择诊断写入字段级步骤结果。

#### Scenario: 报告物资分类参照树上下文和选择结果
- **WHEN** `editable_table.fill_row` 成功录入 `物资分类`，且字段值包含 `tree` 和 `first_available`
- **THEN** 字段级结果 MUST 保留原有 `column`、`value`、列身份和定位来源诊断
- **AND** 字段级结果 SHALL 包含 `selected`
- **AND** 如果运行时应用了参照内树上下文，字段级结果 MUST 包含 `popup_tree_context`
- **AND** 如果运行时点击了确认按钮，字段级结果 MUST 包含 `confirmed` 和可用的 `confirm_label`
- **AND** 字段级结果 SHALL 包含实际 `first_available` 候选诊断，至少能判断候选类型、候选文本摘要、是否来自右侧候选表格行、是否要求选择态以及选择态校验结果

#### Scenario: 普通文本和数字列不增加参照诊断
- **WHEN** `editable_table.fill_row` 成功录入普通文本列或数字列
- **AND** 该字段值不是结构化弹出参照目标
- **THEN** 字段级结果 MUST NOT 添加空的 `selected`、`popup_tree_context`、`confirmed` 或 `confirm_label`
- **AND** 普通文本和数字录入行为 SHALL 保持既有语义

### Requirement: 树表弹出参照支持右表列精确匹配
系统 MUST 在 `editable_table.fill_row` 的结构化弹出参照目标中支持 `tree + match` 组合：先应用弹窗内树上下文，再在同一活动参照弹窗的右侧候选表格中按 `match.column` 和目标值精确选择候选行。

#### Scenario: 物资分类按物资编码精确选择
- **WHEN** DSL 文档执行 `editable_table.fill_row`，目标表格为 `物资入库`
- **AND** 字段 `物资分类` 的模板列组件为 `YDFInput`
- **AND** 字段值包含 `tree.label: A05040101 复印纸`
- **AND** 字段值包含 `match.column: 物资编码` 和 `match.equals: A050401010000000001`
- **THEN** 运行时 MUST 将该字段值视为结构化弹出参照目标
- **AND** 运行时 MUST 打开或复用当前可见的物资类别参照弹窗
- **AND** 运行时 MUST 在该弹窗内选择 `A05040101 复印纸` 树上下文
- **AND** 运行时 MUST 在右侧候选表格中找到 `物资编码` 列值为 `A050401010000000001` 的候选行并选中
- **AND** 运行时 MUST 确认参照或等待目标单元格回填
- **AND** 运行时 MUST NOT 因候选表格使用 W table 渲染形态而报告 `headerCount=0` 或 `strictRowCount=0`

#### Scenario: 树上下文刷新后重新解析右表候选
- **WHEN** 结构化弹出参照目标先应用 `tree` 上下文
- **AND** 左树选择导致右侧候选表格异步刷新或重新渲染
- **THEN** 运行时 MUST 在执行 `match` 前重新解析当前活动参照弹窗内的候选根
- **AND** 运行时 MUST 等待右侧候选表格达到可匹配状态
- **AND** 运行时 MUST NOT 只在左树区域或刷新前的旧候选根内执行 `match`

### Requirement: 树表弹出参照精确匹配诊断
系统 SHALL 在树表弹出参照 `match` 选择失败时输出可判断根因的候选表格诊断，避免把运行时 DOM 识别失败误判为业务数据不存在。

#### Scenario: 目标行可见但未被识别时输出右表诊断
- **WHEN** 运行时已应用弹窗内 `tree` 上下文
- **AND** 字段值包含 `match.column` 和目标值
- **AND** 运行时未能选中目标候选行
- **THEN** 错误信息 MUST 包含目标列名、目标值、可见候选表头摘要、候选行摘要和截图路径
- **AND** 如果候选表格根未被识别，错误诊断 MUST 能体现候选表头数或候选行数为空
- **AND** 运行时 MUST 在当前字段失败，MUST NOT 继续录入后续列并把失败延迟到其他字段

### Requirement: 树表弹出参照 first_available 右表行优先
系统 MUST 在 `editable_table.fill_row` 的结构化弹出参照目标中，将 `tree + first_available` 解释为“先应用弹窗内树上下文，再选择该上下文下右侧候选表格的第一条有效数据行”。

#### Scenario: 右侧候选表格存在时选择第一条数据行
- **WHEN** DSL 文档执行 `editable_table.fill_row`，目标表格为 `物资入库`
- **AND** 字段 `物资分类` 的值包含 `tree.label: A05040101 复印纸` 和 `first_available: true`
- **AND** 当前活动参照弹窗包含左侧树和右侧候选表格
- **THEN** 运行时 MUST 先应用 `A05040101 复印纸` 树上下文
- **AND** 运行时 MUST 在同一活动参照弹窗的右侧候选表格中选择第一条有效数据行
- **AND** 运行时 MUST NOT 将左树节点、表头、分页、查询区、footer 按钮或普通文本节点作为最终 `first_available` 候选

#### Scenario: 右表候选未选中时当前字段失败
- **WHEN** 活动参照弹窗包含可见右侧候选表格
- **AND** `first_available` 未能选中右侧候选表格的数据行或等价选择控件
- **THEN** 当前 `editable_table.fill_row` 字段 MUST 失败
- **AND** 错误信息 MUST 包含候选表格识别摘要、候选行数量、实际尝试候选类型和截图路径
- **AND** 运行时 MUST NOT 继续录入后续列并把失败延迟到保存校验

#### Scenario: 普通树或列表参照保持兼容
- **WHEN** 活动参照弹窗不存在可见右侧候选表格数据行
- **AND** 参照形态是普通树、普通列表或普通下拉候选
- **THEN** `first_available` SHALL 保持既有普通候选选择语义
- **AND** 运行时 MUST 继续要求候选点击后能关闭弹窗、回填目标字段或呈现可识别选择态

### Requirement: 可编辑表格参照列必须解析当前字段候选层
系统 MUST 在 `editable_table.fill_row` 录入可编辑表格弹出参照列时，只能在当前字段触发或当前有效候选参照层内执行过滤、`first_available`、`match` 或确认操作。

#### Scenario: 收款方户名 first_available 不使用主页面文本
- **WHEN** DSL 文档执行 `editable_table.fill_row`，目标表格为 `汇款转账`
- **AND** 字段 `收款方户名` 的模板列组件为 `YDFReferSelect` 或等价 `dataType=refer`
- **AND** 字段值包含 `filter: 严巴天` 和 `first_available: true`
- **AND** 当前页面背景区域包含 `关联单据`、`借款信息`、`借款单号`、`本次核销金额` 或其他非候选参照文本
- **THEN** 运行时 MUST 点击 `收款方户名` 单元格自身的参照触发控件并解析该字段打开的候选参照根
- **AND** 运行时 MUST NOT 将背景页面、当前编辑页内容卡片、业务助手或已关闭旧弹层作为 `收款方户名` 的候选参照根
- **AND** 运行时 MUST NOT 在这些背景文本中查找 `严巴天` 或第一条可用候选

#### Scenario: 未打开当前字段候选层时在当前字段失败
- **WHEN** `editable_table.fill_row` 的目标字段值包含 `first_available`、`match`、`row_number`、`selections` 或其他结构化弹出参照语义
- **AND** 运行时点击目标单元格后无法打开或解析当前字段的有效候选参照根
- **THEN** 当前 `editable_table.fill_row` 步骤 MUST 在该字段失败
- **AND** 错误信息 MUST 包含表格名、行号、列名、字段组件、结构化目标摘要和可见页面或前景层诊断
- **AND** 错误信息 MUST 指向参照候选层未打开或未解析，而不是报告在背景页面中未找到候选值

#### Scenario: 成功选择后报告当前候选层诊断
- **WHEN** `editable_table.fill_row` 成功录入可编辑表格弹出参照列
- **AND** 字段值包含 `filter` 和 `first_available`
- **THEN** 字段级结果 SHALL 保留列身份和定位来源诊断
- **AND** 字段级结果 SHALL 包含实际选择候选的诊断，至少能判断候选来源不是背景页面文本
- **AND** 如果参照候选层自动关闭且目标单元格已回填，系统 MUST 按既有自动关闭回填规则判定该字段成功

### Requirement: 可编辑表格结构化参照修复不得回退既有树表能力
系统 MUST 保持可编辑表格结构化弹出参照目标的既有能力，包括 `tree + first_available`、`tree + match`、`match.contains`、`row_number` 和 `selections`。

#### Scenario: 树表 first_available 仍选择右侧候选行
- **WHEN** 可编辑表格字段值包含 `tree` 和 `first_available: true`
- **AND** 当前有效候选参照根包含左树和右侧候选表格
- **THEN** 运行时 MUST 先应用树上下文
- **AND** 运行时 MUST 继续优先选择右侧候选表格中的第一条有效数据行
- **AND** 运行时 MUST NOT 为修复普通 `YDFReferSelect` 回归而退回点击左树节点、普通文本节点或把对象字符串化写入单元格

#### Scenario: 树表 match 与 contains 保持兼容
- **WHEN** 可编辑表格字段值包含 `tree` 和 `match.column`
- **AND** `match` 使用 `equals` 或 `contains`
- **THEN** 运行时 MUST 继续在当前有效候选参照根内按右侧候选表格匹配目标行
- **AND** 运行时 MUST 保持 W table、分离表头表体、候选行选择态和确认回填的既有语义

### Requirement: 可编辑表格单元格限定到前景目标表格
系统 MUST 在执行 `editable_table.fill_row` 定位单元格时，将行和单元格搜索限定到当前前景可操作的目标可编辑表格；背景列表、旧模板残留表格、业务助手 iframe、非目标表格或被遮挡表格不得参与目标行选择。

#### Scenario: 连续运行后不串到上一轮待提交列表行
- **WHEN** DSL 文档执行 `editable_table.fill_row`，目标表格为 `物资信息`，`row_number: -1`
- **AND** 当前新增页前景包含 `物资信息` 可编辑子表，子表中有一条已通过 `物资分类` 参照回填的行
- **AND** 页面 DOM 中仍存在上一轮保存出的待提交列表行，例如包含 `LY202600000001` 和旧申请事由
- **THEN** 系统 MUST 在前景 `物资信息` 子表内解析 `row_number: -1`
- **AND** 系统 MUST 激活该子表行的 `申请数量` 单元格
- **AND** 系统 MUST NOT 将背景待提交列表行作为 `editable_table.fill_row` 的目标行

#### Scenario: 目标表格 root 为空时当前字段失败
- **WHEN** DSL 文档执行 `editable_table.fill_row`，且目标表格名或模板列身份能解析出目标 `tableFieldid`
- **AND** 运行时找不到当前前景可操作的目标表格 root 或目标 root 内没有可编辑数据行
- **THEN** 当前 `editable_table.fill_row` 步骤 MUST 在当前字段失败
- **AND** 错误信息 MUST 包含目标表格名、目标 `tableFieldid`、候选 root 摘要和可见表格诊断
- **AND** 系统 MUST NOT 继续扫描背景列表或其他表格并把其中的行当作目标行

### Requirement: 可编辑表格串表诊断
系统 SHALL 在可编辑表格单元格定位失败或编辑器缺失时输出足够诊断，用于区分目标子表无编辑器、目标 root 未找到、命中背景列表行和业务数据缺失。

#### Scenario: 编辑器缺失时报告实际命中的 root 和 row
- **WHEN** `editable_table.fill_row` 已定位到某个候选单元格
- **AND** 激活该单元格后没有出现可输入控件
- **THEN** 错误信息 SHALL 包含目标表格名、目标列名、目标 `tableFieldid`、定位来源、候选 root 摘要、被选中 row 文本和 row index
- **AND** 如果候选 row 文本不属于目标前景表格，诊断 SHOULD 能体现该 row 来自背景或非目标表格

#### Scenario: 成功录入时保留目标表格定位诊断
- **WHEN** `editable_table.fill_row` 成功录入普通文本列、数字列或结构化参照列
- **THEN** 字段级结果 SHALL 保留既有列身份信息，例如 `fieldid`、`data_field`、`table_fieldid` 和 `locator_source`
- **AND** 字段级结果 SHALL 包含足以判断目标 root 的诊断字段，例如 root 来源、目标表格身份或等价摘要
- **AND** 普通文本和数字列录入行为 MUST 保持既有语义

### Requirement: 可编辑表格单元格激活避开行级动作浮层
系统 MUST 在执行 `editable_table.fill_row` 激活目标单元格时，避开 hover 后覆盖在单元格区域上的行级动作按钮或更多按钮，并点击能够进入编辑态的真实单元格区域。系统 SHALL 在需要临时收起当前行按钮组才能激活目标单元格时，将收起动作限定在当前目标表格和当前目标行，并在字段录入确认后尝试恢复默认行按钮显示行为。

#### Scenario: 行级动作浮层覆盖文本列时仍激活编辑器
- **WHEN** DSL 文档执行 `editable_table.fill_row`，目标表格为 `测算信息`
- **AND** 目标行在 hover 或前序录入后显示 `插入`、`复制`、`删除` 或更多行级动作浮层
- **AND** 字段 `测算依据及说明` 的模板列组件为 `YDFInput`，且目标列身份为 `estDesc`
- **THEN** 运行时 MUST 避开行级动作按钮和更多按钮，激活 `estDesc` 对应的单元格编辑器
- **AND** 运行时 MUST 将 DSL 值录入 `测算依据及说明` 单元格
- **AND** 运行时 MUST NOT 因点击到行级动作浮层而报告 `可编辑表格单元格激活后未出现可输入控件`

#### Scenario: 临时收起当前行按钮后录入并恢复默认行为
- **WHEN** DSL 文档执行 `editable_table.fill_row`，目标表格为 `需求清单`
- **AND** 目标列为 `备注`，目标列身份为 `cgbd_table_remark`
- **AND** 目标行的行级动作按钮组覆盖 `备注` 单元格点击区域
- **AND** 同一目标行行按钮组最右侧存在可收起该按钮组的入口
- **THEN** 运行时 MUST 点击该入口临时收起当前行按钮组
- **AND** 运行时 MUST 重新定位 `cgbd_table_remark` 对应的目标单元格并激活编辑器
- **AND** 运行时 MUST 将 DSL 值录入 `备注` 单元格并确认回填
- **AND** 运行时 SHALL 在回填确认后尝试恢复当前表格当前行的默认行按钮显示行为
- **AND** 运行时 MUST NOT 改变其他表格的行按钮显示状态

#### Scenario: 恢复默认行为失败时保留录入结果和诊断
- **WHEN** `editable_table.fill_row` 已通过临时收起行按钮组完成目标字段录入
- **AND** 目标单元格已确认回填 DSL 值
- **AND** 运行时无法恢复当前行按钮默认显示行为
- **THEN** 当前字段录入结果 SHALL 保留成功回填结果
- **AND** 诊断 SHALL 记录行按钮恢复失败信息
- **AND** 后续字段或后续步骤 MUST 继续基于当前运行时 DOM 重新定位目标，不得复用收起前的旧 locator

#### Scenario: 遮挡无法避开时保留可诊断失败
- **WHEN** 目标单元格被前景浮层或业务控件完全遮挡，运行时无法找到可激活编辑器的点击点
- **THEN** 当前 `editable_table.fill_row` 步骤 MUST 在该字段失败
- **AND** 错误信息 MUST 包含表格名、行号、列名、目标列身份或定位来源
- **AND** 错误信息 SHALL 包含截图路径或等价遮挡诊断，便于区分真实不可编辑列与点击点被遮挡

### Requirement: 可编辑表格新增行按目标表格身份定位
系统 SHALL 在执行 `editable_table.add_row` 时将 `target.table` 解析为当前前景可编辑表格身份，并用该身份限定运行时新增入口；当页面分组标题、模板表格 label 和运行时可见表头文本不一致时，系统仍 MUST 在能唯一解析目标表格的情况下点击正确的新增入口。

#### Scenario: 分组标题匹配到模板表格新增入口
- **WHEN** DSL 文档执行 `editable_table.add_row`，`target.table` 为页面分组标题 `缴款明细信息`
- **AND** 当前模板中唯一对应的可编辑表格 label 为 `缴库明细表格`
- **AND** 运行时 DOM 中目标表格附近只稳定显示列头 `缴款金额`、`政府非税收入项目`、`收入分类` 和 `备注`
- **THEN** 系统 MUST 将 `缴款明细信息` 解析到该目标可编辑表格
- **AND** 系统 MUST 在该目标表格作用域内点击 `新增`
- **AND** 系统 MUST NOT 因运行时 DOM 缺少 `缴款明细信息` 或 `缴库明细表格` 可见文本而拒绝点击

#### Scenario: 模板表格名不依赖运行时可见标题
- **WHEN** DSL 文档执行 `editable_table.add_row`，`target.table` 为模板表格 label `缴库明细表格`
- **AND** 运行时目标表格附近没有可见的 `缴库明细表格` 标题
- **THEN** 系统 MUST 使用模板表格身份、表格 fieldid、列身份或等价目标 root 约束新增入口
- **AND** 系统 MUST NOT 只因附近标题匹配分数不足而报告 `可编辑表格名称未匹配`

#### Scenario: 后续行录入复用同一表格身份
- **WHEN** DSL 文档先执行 `editable_table.add_row`，再执行 `editable_table.fill_row`
- **AND** 两个步骤的 `target.table` 都为页面分组标题 `缴款明细信息`
- **AND** 当前模板中唯一对应的可编辑表格 label 为 `缴库明细表格`
- **THEN** 系统 MUST 在两个步骤中都将 `缴款明细信息` 解析到同一个目标可编辑表格
- **AND** `editable_table.fill_row` MUST 使用解析后的表格身份定位列和行

#### Scenario: 多个候选表格无法唯一解析时失败
- **WHEN** DSL 文档执行 `editable_table.add_row` 且提供了 `target.table`
- **AND** executor 或 runtime 找到多个可编辑表格候选，无法唯一判断哪个候选属于该目标
- **THEN** 当前 `editable_table.add_row` 步骤 MUST 失败
- **AND** 错误信息 MUST 包含 `target.table`、候选表格 label、候选 fieldid 或可见表头摘要

### Requirement: 可编辑表格新增行成功必须验证真实数据行
系统 MUST 在 `editable_table.add_row` 点击新增入口后验证目标可编辑表格出现真实可编辑数据行；如果目标表格仍为空态、仍显示 `暂无数据`，或没有可用于后续 `editable_table.fill_row` 的数据行，当前新增行步骤 MUST 失败并输出诊断。如果目标表格已有数据行，点击后目标表格真实数据行数量没有增加，且没有打开行编辑表单模板，当前新增行步骤 MUST 失败并输出诊断。

#### Scenario: 点击新增后出现可编辑行才成功
- **WHEN** DSL 文档执行 `editable_table.add_row`
- **AND** 运行时点击了目标表格作用域内的 `新增`
- **AND** 目标表格从空态变为包含真实数据行，例如第一行显示序号 `1`
- **THEN** 当前步骤 MUST 报告成功
- **AND** 步骤结果 SHALL 包含目标表格身份、点击入口诊断和新增后的行状态摘要

#### Scenario: 点击后仍是暂无数据时当前步骤失败
- **WHEN** DSL 文档执行 `editable_table.add_row`
- **AND** 运行时点击了某个 `新增` 入口
- **AND** 等待后目标表格仍只包含 `暂无数据` 或没有可编辑数据行
- **THEN** 当前步骤 MUST 失败
- **AND** 错误信息 MUST 指向新增行未生效
- **AND** 系统 MUST NOT 将该步骤报告为成功并把失败延迟到后续 `editable_table.fill_row`

#### Scenario: 未指定表格名保持单表兼容
- **WHEN** DSL 文档执行 `editable_table.add_row` 且未提供 `target.table`
- **AND** 当前前景页面只有一个可识别的可编辑表格新增入口
- **THEN** 系统 SHALL 保持既有点击语义
- **AND** 系统 MUST 仍执行新增后真实数据行校验

#### Scenario: 非空表格点击新增后行数未增长时失败
- **WHEN** DSL 文档执行 `editable_table.add_row`，目标表格为 `需求清单`
- **AND** 点击前目标表格已有 1 条真实数据行
- **AND** 运行时点击了某个 `新增` 入口后没有打开行编辑表单模板
- **AND** 等待后目标表格仍只有 1 条真实数据行
- **THEN** 当前 `editable_table.add_row` 步骤 MUST 失败
- **AND** 错误信息 MUST 指向新增行未生效，并包含点击前后行数摘要
- **AND** 系统 MUST NOT 将该步骤报告为成功并把同一行交给后续 `editable_table.fill_row` 重复维护

### Requirement: 可编辑表格单元格激活必须命中编辑入口
系统 MUST 在 `editable_table.fill_row` 已经定位到目标表格、目标行和目标列后，尝试命中目标单元格的编辑入口。系统 SHALL 以运行时反馈判断字段是否可录入，MUST NOT 仅依据模板 `disabled` 标记或激活前没有内嵌输入控件判断字段不可录入。

#### Scenario: 展示态字段进入编辑态后录入
- **WHEN** DSL 文档执行 `editable_table.fill_row`，目标表格为 `指标信息调剂表`
- **AND** 目标字段为 `单位内部机构`，目标单元格当前显示 `秘书处01`
- **AND** 人工操作同一单元格可以进入编辑态并选择 `101001 秘书处01`
- **THEN** 运行时 MUST 尝试通过目标单元格的可操作区域进入编辑态
- **AND** 运行时 MUST 在进入编辑态后按照 DSL 值完成录入或选择
- **AND** 运行时 MUST NOT 在未充分尝试激活前报告该列不可输入

#### Scenario: 行级动作不应阻断单元格编辑
- **WHEN** 目标行附近存在 `删除`、`插入`、`复制` 或更多行级动作
- **AND** 这些动作位于目标单元格附近
- **THEN** 运行时 MUST 避免把行级动作作为目标字段编辑入口
- **AND** 运行时 MUST 继续尝试目标单元格自身的编辑入口

### Requirement: 可编辑表格单元格激活必须识别当前字段候选层
系统 SHALL 在目标单元格激活后识别当前字段产生的候选层、下拉层、参照层或获得焦点的编辑控件，即使该控件不是目标单元格 DOM 的后代。

#### Scenario: 候选层出现后继续字段录入
- **WHEN** 运行时激活目标单元格后，单元格内部没有新增 `input`、`textarea` 或 `contenteditable`
- **AND** 当前字段产生了可见候选层或获得焦点的编辑控件
- **THEN** 运行时 MUST 将目标字段视为已进入可录入状态
- **AND** 运行时 MUST 按字段值类型继续执行普通选择、参照选择或结构化参照选择

#### Scenario: 无关页面浮层不应被当作当前字段候选层
- **WHEN** 目标单元格激活前页面已存在导航、方案或其他无关浮层
- **AND** 激活后这些浮层没有与目标字段形成新的候选状态
- **THEN** 运行时 MUST NOT 将这些既有浮层作为当前字段候选层
- **AND** 运行时 MUST 继续尝试激活目标字段或输出激活失败诊断

### Requirement: 可编辑表格单元格激活失败必须提供根因诊断
系统 SHALL 在目标单元格激活失败时提供足够诊断，用于区分目标定位错误、目标行错误、字段真实不可编辑、编辑入口未命中、行级动作遮挡和候选层未出现。

#### Scenario: 正确单元格仍未进入编辑态时输出诊断
- **WHEN** `editable_table.fill_row` 已定位到目标表格、目标行和目标列
- **AND** 运行时完成全部激活尝试后仍未进入可录入状态
- **THEN** 当前字段 MUST 失败
- **AND** 错误信息 MUST 包含目标表格、行号、列名、列身份、定位来源、单元格文本和行文本摘要
- **AND** 错误信息 SHALL 包含激活尝试摘要、当前焦点摘要、可见候选层摘要和截图路径

#### Scenario: 成功录入时保留必要诊断
- **WHEN** 运行时成功激活并录入可编辑表格目标字段
- **THEN** 字段级结果 SHALL 保留目标列身份和定位来源
- **AND** 字段级结果 MUST NOT 写入大量 DOM 快照或无关页面文本

### Requirement: 可编辑表格商品参照 first_available 选择当前可见业务行
系统 MUST 在 `editable_table.fill_row` 录入可编辑表格参照列时，将结构化目标 `first_available: true` 应用于当前字段打开的有效候选参照层，并选择当前可见候选表格中的第一条业务数据行。

#### Scenario: 发票内容明细商品参照选择首条商品
- **WHEN** DSL 执行 `editable_table.fill_row`
- **AND** 目标表格为 `发票内容明细`
- **AND** 字段 `商品` 的组件为 `YDFTableModalSelect`
- **AND** 字段值为 `first_available: true`
- **AND** 当前商品参照弹窗显示一条可见业务行 `0702154531736 / 商品_0702154531736`
- **THEN** runtime MUST 在当前商品参照弹窗内选择该业务行
- **AND** runtime MUST 等待 `商品` 单元格回填或确认参照选择完成
- **AND** 当前 `editable_table.fill_row` MUST NOT 因空状态候选、背景页面文本或非当前字段候选层而失败

#### Scenario: 当前字段候选层优先于背景和旧弹层
- **WHEN** 前景业务弹窗、背景页面或旧弹层中存在其它表格、空状态或说明文本
- **AND** 当前 `editable_table.fill_row` 字段已打开新的商品候选参照层
- **THEN** runtime MUST 在当前字段候选参照层内执行 `first_available`
- **AND** runtime MUST NOT 将背景页面、外层业务表单、业务助手 iframe 或已关闭旧弹层作为商品候选根

### Requirement: 可编辑表格 first_available 失败诊断区分空状态和业务行
系统 SHALL 在可编辑表格参照列 `first_available` 失败时输出能区分业务无数据、空状态被排除、业务行未选中和候选根识别错误的字段级诊断。

#### Scenario: 业务行可见但候选未选中
- **WHEN** 商品参照弹窗诊断文本能读取到业务行 `0702154531736 / 商品_0702154531736`
- **AND** runtime 未能选中该行
- **THEN** 当前字段失败信息 MUST 包含表格名、行号、列名、组件类型和结构化目标
- **AND** 诊断 SHALL 包含有效候选数量、实际尝试候选、候选来源、候选文本摘要和截图路径
- **AND** 诊断 MUST NOT 只报告空状态候选而不暴露可见业务行摘要

#### Scenario: 真实无业务候选
- **WHEN** 当前商品候选参照层只包含空状态或查询后无结果
- **THEN** 当前字段失败信息 MUST 明确说明没有有效业务候选
- **AND** runtime MUST 保留空状态文本或截图，避免误导为 DSL 写法错误

### Requirement: 可编辑表格字段支持父表头限定
系统 SHALL 允许 `editable_table.fill_row` 的字段声明携带父表头限定，用于在同一目标表格内区分同名明细列。

#### Scenario: 对象字段值声明父表头
- **WHEN** DSL 文档执行 `editable_table.fill_row`
- **AND** `target.fields` 使用对象写法，字段 `当年财政拨款(万元)` 的值为包含 `column_group: 全年执行决算金额` 和 `value: 3` 的对象
- **THEN** 系统 MUST 将 `当年财政拨款(万元)` 作为叶子列名
- **AND** 系统 MUST 将 `全年执行决算金额` 作为该字段的父表头限定
- **AND** 系统 MUST 将 `3` 作为实际录入值

#### Scenario: 普通字段和父表头字段混合录入
- **WHEN** DSL 文档在同一个 `editable_table.fill_row` 步骤中同时包含普通字段 `备注: 测试` 和字段值包装器 `当年财政拨款(万元): {column_group: 全年执行决算金额, value: 3}`
- **THEN** 系统 MUST 保持 `备注` 的既有普通列定位和录入语义
- **AND** 系统 MUST 仅对 `当年财政拨款(万元)` 应用父表头限定

#### Scenario: 父表头字段包装结构化参照值
- **WHEN** DSL 文档执行 `editable_table.fill_row`
- **AND** 字段 `项目目录` 的值包含 `column_group: 项目信息`
- **AND** 字段真实值位于 `value` 中，且 `value` 包含 `tree`、`match` 或 `first_available` 等结构化参照目标
- **THEN** 系统 MUST 使用 `column_group` 定位目标列
- **AND** 系统 MUST 将 `value` 内的对象按既有结构化参照目标处理
- **AND** 系统 MUST NOT 将字段包装器整体字符串化写入单元格

#### Scenario: 列表字段项声明父表头
- **WHEN** DSL 文档执行 `editable_table.fill_row`
- **AND** `target.fields` 使用列表写法，某项包含 `field: 当年财政拨款(万元)`、`column_group: 全年执行决算金额` 和 `equals: 3`
- **THEN** 系统 MUST 将该列表项解释为叶子列 `当年财政拨款(万元)` 在父表头 `全年执行决算金额` 下录入 `3`

### Requirement: 父表头限定支持多级路径
系统 SHALL 支持 `column_group` 使用字符串或字符串列表表达父表头限定；列表形式 MUST 从外层父表头到内层父表头匹配，不包含叶子列名。

#### Scenario: 单级父表头字符串
- **WHEN** DSL 文档中字段包装器包含 `column_group: 全年执行决算金额`
- **THEN** 系统 MUST 将其归一化为父表头路径 `["全年执行决算金额"]`

#### Scenario: 多级父表头列表
- **WHEN** DSL 文档中字段包装器包含 `column_group: [资金金额, 全年执行决算金额]`
- **THEN** 系统 MUST 按 `资金金额` 到 `全年执行决算金额` 的顺序匹配目标列的父表头路径
- **AND** 系统 MUST NOT 要求列表中重复包含叶子列名

### Requirement: 同名明细列必须可判定或失败
系统 MUST 在 `editable_table.fill_row` 解析目标列时避免对同名明细列做隐式猜测；如果无法根据叶子列名、目标表格和父表头限定唯一确定目标列，当前步骤 MUST 失败。

#### Scenario: 同名列未提供父表头限定
- **WHEN** 目标表格中存在多个叶子列名均为 `当年财政拨款(万元)` 的可见或可绑定列
- **AND** DSL 文档只写 `fields: {当年财政拨款(万元): 3}`，未提供 `column_group`
- **THEN** 当前 `editable_table.fill_row` 步骤 MUST 失败
- **AND** 错误信息 MUST 包含目标叶子列名和可用父表头路径摘要
- **AND** 系统 MUST NOT 默认写入第一个同名列

#### Scenario: 父表头限定后唯一命中
- **WHEN** 目标表格中存在 `全年执行自评金额 > 当年财政拨款(万元)` 和 `全年执行决算金额 > 当年财政拨款(万元)` 两个叶子列
- **AND** DSL 文档为字段 `当年财政拨款(万元)` 提供 `column_group: 全年执行决算金额`
- **THEN** 系统 MUST 选择 `全年执行决算金额 > 当年财政拨款(万元)` 对应的模板列身份或 DOM 单元格
- **AND** 系统 MUST NOT 写入 `全年执行自评金额 > 当年财政拨款(万元)` 对应单元格

#### Scenario: 父表头限定仍不唯一
- **WHEN** 目标表格中多个候选列都匹配叶子列名和 `column_group`
- **THEN** 当前字段 MUST 失败
- **AND** 错误信息 MUST 包含所有冲突候选的父表头路径和可用列身份摘要

### Requirement: 父表头定位诊断可追踪
系统 SHALL 在父表头限定参与 `editable_table.fill_row` 定位时，在成功或失败诊断中暴露目标父表头路径、实际命中列身份和定位来源。

#### Scenario: 成功报告父表头路径
- **WHEN** `editable_table.fill_row` 成功录入带 `column_group` 的字段
- **THEN** 字段级结果 SHALL 保留原有 `column`、`value`、`fieldid`、`data_field` 和 `table_fieldid`
- **AND** 字段级结果 SHALL 包含目标父表头路径或等价诊断字段
- **AND** 字段级结果 SHALL 包含实际定位来源，例如模板身份、DOM 多表头几何兜底或现有身份单元格定位来源

#### Scenario: DOM 多表头兜底报告候选路径
- **WHEN** 模板中无法解析目标列父表头路径
- **AND** runtime 通过真实 DOM 多行表头几何关系完成目标列定位
- **THEN** 字段级结果 SHALL 标记该字段使用 DOM 表头路径兜底
- **AND** 失败诊断 MUST 包含当前目标表格内可识别的表头路径摘要

### Requirement: 可编辑表格 table 作用域支持语义标题和表身份
系统 SHALL 在执行 `editable_table.add_row` 或 `editable_table.fill_row` 时，将 `target.table` 解析为当前模板中的目标可编辑表格作用域，并支持用户使用可见语义标题、表 region `fieldid` 或 runtime fieldid 定位目标表格。

#### Scenario: 使用父卡片标题定位可编辑表格
- **WHEN** DSL 文档执行 `editable_table.fill_row`
- **AND** `target.table` 为用户界面可见的父卡片标题 `指标挂接规则`
- **AND** 当前模板中该父卡片下唯一可编辑表格的 region `fieldid` 为 `table_rule`
- **THEN** 系统 MUST 将该步骤限定到 `table_rule` 对应的可编辑表格
- **AND** 系统 MUST 继续使用该表格的模板列身份定位目标单元格

#### Scenario: 父标题下同时存在编辑表和展示表
- **WHEN** DSL 文档执行 `editable_table.fill_row`
- **AND** `target.table` 为父卡片标题 `指标挂接规则`
- **AND** 当前模板中 `table_rule` 和 `table_rule_view` 均位于该父卡片下且均包含列 `部门支出经济分类`
- **AND** 当前运行时 DOM 中只有 `table_rule` 对应表根存在且可见
- **THEN** 系统 MUST 将该步骤限定到 `table_rule` 对应的可编辑表格
- **AND** 系统 MUST NOT 因父标题匹配到多张表而拒绝该步骤

#### Scenario: 父标题下多张候选表同时可见时要求显式 fieldid
- **WHEN** DSL 文档执行 `editable_table.fill_row`
- **AND** `target.table` 为父卡片标题 `指标挂接规则`
- **AND** 当前模板中 `table_rule` 和 `table_rule_view` 均位于该父卡片下
- **AND** 当前运行时 DOM 中 `table_rule` 和 `table_rule_view` 对应表根都存在且可见
- **THEN** 当前步骤 MUST 失败
- **AND** 错误信息 MUST 提示这种情况下必须使用表 region `fieldid` 或 runtime fieldid 标识目标表格
- **AND** 系统 MUST NOT 继续依据列属性、列名或候选顺序猜测目标表格

#### Scenario: 使用 runtime fieldid 定位可编辑表格
- **WHEN** DSL 文档执行 `editable_table.fill_row`
- **AND** `target.table` 为目标表格的 runtime fieldid `table_rule_table`
- **AND** 当前模板中存在 region `fieldid=table_rule` 且其 `runtime_fieldids` 包含 `table_rule_table`
- **THEN** 系统 MUST 将该步骤限定到 `table_rule` 对应的可编辑表格
- **AND** 系统 MUST NOT 因表 region 的显示 label 为泛名 `表格` 而拒绝该步骤

#### Scenario: 表名不匹配时提示可用 fieldid
- **WHEN** DSL 文档执行 `editable_table.fill_row`
- **AND** `target.table` 未匹配当前模板中的任何可编辑表格作用域
- **THEN** 当前步骤 MUST 失败
- **AND** 错误信息 MUST 列出当前模板可用可编辑表格的 label、region `fieldid` 和 runtime fieldid
- **AND** 错误信息 MUST NOT 只重复输出多个无区分度的 `表格`

#### Scenario: 父级语义标题不唯一且运行时不可判定时不猜测
- **WHEN** DSL 文档执行 `editable_table.fill_row`
- **AND** `target.table` 匹配多个可编辑表格共享的父级语义标题
- **AND** 运行时 DOM 无法判定唯一可见目标表格
- **THEN** 当前步骤 MUST 失败
- **AND** 错误信息 MUST 列出冲突候选的 label、region `fieldid` 和 runtime fieldid
- **AND** 系统 MUST NOT 任意选择第一张匹配表格

### Requirement: 可编辑表格新增行验证限定目标表格
系统 MUST 在执行 `editable_table.add_row` 时，将点击后的新增行验证限定到 DSL 解析出的目标可编辑表格身份、目标 `fieldid` 或等价目标 root；目标表格外的相邻表格、外层表单容器、背景列表和其他明细表行不得作为当前新增成功证据。

#### Scenario: 相邻表格已有行不能证明目标新增成功
- **WHEN** DSL 文档执行 `editable_table.add_row`，目标表格为 `需求清单`
- **AND** executor 已将目标表格解析为 `table_fieldid=cgbd_table`
- **AND** 页面同一表单区域内存在其他可编辑表格或明细表，且这些表格已有 `公司业绩`、`交付时间`、`产品质保` 等数据行
- **AND** 点击 `需求清单` 区域的 `新增` 后，`需求清单` 仍只显示空态、表头或 `+ 新增`
- **THEN** 当前 `editable_table.add_row` 步骤 MUST 失败
- **AND** 系统 MUST NOT 将相邻表格的已有数据行计入 `需求清单` 的新增后 `row_state`
- **AND** 系统 MUST NOT 把失败延迟到后续 `editable_table.fill_row`

#### Scenario: 目标表格出现真实可编辑行才报告成功
- **WHEN** DSL 文档执行 `editable_table.add_row`
- **AND** 运行时已根据 `target.table`、目标表格 `fieldid` 或目标列身份定位到目标表格 root
- **AND** 点击新增入口后，目标表格 root 内出现可供后续 `editable_table.fill_row` 定位的真实数据行
- **THEN** 当前步骤 MUST 报告成功
- **AND** 步骤结果 SHALL 包含目标表格身份、点击入口诊断和限定在目标表格 root 内的新增后 `row_state`

#### Scenario: 无法唯一确认目标验证 root 时失败
- **WHEN** DSL 文档执行 `editable_table.add_row` 且提供了 `target.table`
- **AND** 运行时点击了候选新增入口，但无法将点击后的验证 root 唯一限定到目标表格身份、目标 `fieldid` 或目标列身份
- **THEN** 当前步骤 MUST 失败
- **AND** 错误信息 MUST 包含 `target.table`、目标 `table_fieldid` 或目标列身份摘要，以及候选 root 的可见文本或行状态摘要

### Requirement: 可编辑表格重复新增前收口交互状态

系统 SHALL 在执行 `editable_table.add_row` 时，优先利用已解析目标表格身份定位新增入口；当目标表格存在 `table_fieldid` 时，系统 SHALL 优先查找并点击 `${table_fieldid}_add_button` 对应的可见 fieldid 入口。系统 SHALL 在点击目标表格新增入口前收口当前可编辑表格的残留交互状态，包括激活单元格编辑态、可见选择下拉和行级悬浮/更多按钮状态；当目标表格已有真实数据行且首次点击后行数未增长、也未打开行编辑表单模板时，系统 SHALL 在同一目标表格作用域内最多重试一次新增点击。重试后仍未增长时，系统 MUST 按新增行未生效失败，不得把同一行交给后续 `editable_table.fill_row` 重复维护。

#### Scenario: 目标表格 fieldid 派生新增入口优先

- **WHEN** DSL 文档执行 `editable_table.add_row`，目标表格解析为 `table_fieldid=cgbd_table`
- **AND** 页面存在可见元素 `fieldid="cgbd_table_add_button"` 或等价 data fieldid
- **THEN** 系统 MUST 优先把该 fieldid 元素作为目标表格新增入口候选
- **AND** 系统 MUST 在点击后仍按目标表格真实数据行增长校验当前步骤是否成功
- **AND** 当该 fieldid 入口不存在或不可见时，系统 SHALL 继续使用表格作用域内的文本候选扫描作为兜底

#### Scenario: 连续填行后再次新增成功

- **WHEN** DSL 文档先执行 `editable_table.add_row`，再执行 `editable_table.fill_row` 录入 `需求清单` 第一行
- **AND** `editable_table.fill_row` 录入最后一个字段后留下激活编辑态、可见选择下拉或行级悬浮/更多按钮状态
- **AND** 下一步再次执行 `editable_table.add_row`，目标表格仍解析为 `table_fieldid=cgbd_table`
- **THEN** 系统 MUST 在点击 `新增` 前收口这些残留交互状态
- **AND** 系统 MUST 优先通过 `fieldid="cgbd_table_add_button"` 定位 `需求清单` 的 `新增` 入口
- **AND** 当目标表格真实数据行从 1 行增长到 2 行时，当前 `editable_table.add_row` 步骤 MUST 报告成功

#### Scenario: 首次新增点击未增长时受控重试

- **WHEN** DSL 文档执行 `editable_table.add_row`，目标表格为 `需求清单`
- **AND** 点击前目标表格已有 1 条真实数据行
- **AND** 首次点击目标表格作用域内的 `新增` 后没有打开行编辑表单模板，且目标表格仍只有 1 条真实数据行
- **THEN** 系统 SHALL 重新收口交互状态并重新解析同一目标表格作用域内的 `新增` 候选
- **AND** 系统 MUST 最多再点击一次同一目标表格作用域内的 `新增`
- **AND** 如果重试后目标表格真实数据行增长，当前 `editable_table.add_row` 步骤 MUST 报告成功，并在步骤结果中保留点击前后行状态摘要

#### Scenario: 重试后仍未增长时失败

- **WHEN** DSL 文档执行 `editable_table.add_row`，目标表格为 `需求清单`
- **AND** 点击前目标表格已有 1 条真实数据行
- **AND** 首次点击和一次受控重试后都没有打开行编辑表单模板
- **AND** 等待后目标表格仍只有 1 条真实数据行
- **THEN** 当前 `editable_table.add_row` 步骤 MUST 失败
- **AND** 错误信息 MUST 指向新增行未生效，并包含点击前后行数、目标表格身份和可用候选诊断
- **AND** 系统 MUST NOT 将该步骤报告为成功并把同一行交给后续 `editable_table.fill_row` 重复维护

### Requirement: 可编辑表格空态 placeholder 新增按目标表格 root 判定
系统 MUST 在执行 `editable_table.add_row` 点击空态 placeholder 新增入口时，将点击前后行状态验证限定到 DSL 解析出的目标表格 root；placeholder 按钮自身、外层表单容器、相邻表格和背景表格不得作为目标表格行状态证据。系统 SHALL 仅在点击前目标表格 root 已可靠确认存在真实数据行时启用一次受控重试；空目标表格首次点击后出现真实可编辑行时 MUST 直接报告成功。

#### Scenario: 空目标表格 placeholder 首次新增成功
- **WHEN** DSL 文档执行 `editable_table.add_row`，目标表格解析为 `table_fieldid=table2`
- **AND** 点击前 `table2` 对应目标表格为空态，只显示 placeholder 新增入口
- **AND** 运行时点击 `.ydf-table-placeholder-add-button` 或等价 placeholder 新增入口
- **AND** 点击后 `table2` 对应目标表格 root 内出现第一条真实可编辑数据行
- **THEN** 当前 `editable_table.add_row` 步骤 MUST 报告成功
- **AND** 系统 MUST NOT 对同一 placeholder 新增入口执行第二次点击
- **AND** 步骤结果 SHALL 包含目标表格身份、候选入口和点击后的目标 root 行状态摘要

#### Scenario: placeholder 按钮不能作为验证 root
- **WHEN** `editable_table.add_row` 选中的候选入口是 `.ydf-table-placeholder-add-button`、`.ydf-table-placeholder-add` 或等价空态新增按钮
- **AND** DSL 目标已经解析出 `target.table`、目标 `table_fieldid` 或目标列身份
- **THEN** 系统 MUST 在点击前后按目标表格身份解析验证 root
- **AND** 系统 MUST NOT 将 placeholder 按钮自身的文本、外层表单容器行数、相邻表格行数或背景表格行数计入目标表格 `row_state`
- **AND** 如果无法唯一确认目标验证 root，当前步骤 MUST 失败并输出目标表格身份、候选入口和候选 root 诊断

#### Scenario: 空态新增后仍无真实行时失败
- **WHEN** DSL 文档执行 `editable_table.add_row`
- **AND** 点击前目标表格 root 为空态
- **AND** 运行时点击目标表格 placeholder 新增入口后，目标表格 root 仍没有真实可编辑数据行
- **THEN** 当前 `editable_table.add_row` 步骤 MUST 失败
- **AND** 错误信息 MUST 指向新增行未生效，并包含目标表格身份、placeholder 候选入口和点击后的目标 root 行状态
- **AND** 系统 MUST NOT 因外层或相邻表格已有行而报告成功

#### Scenario: 非空目标表格未增长时仍可受控重试
- **WHEN** DSL 文档执行 `editable_table.add_row`
- **AND** 点击前系统已可靠确认目标表格 root 内已有 1 条真实数据行
- **AND** 首次点击目标表格新增入口后没有打开行编辑表单模板，且目标表格 root 内仍只有 1 条真实数据行
- **THEN** 系统 SHALL 重新收口交互状态并重新解析同一目标表格作用域内的新增候选
- **AND** 系统 MUST 最多再点击一次同一目标表格作用域内的新增入口
- **AND** 重试后仍未增长时，当前步骤 MUST 失败并保留首次点击和最终点击的行状态诊断

#### Scenario: 不可靠的点击前行数不得触发重试
- **WHEN** `editable_table.add_row` 的首次点击结果显示 `row_state_changed=false`
- **AND** 点击前行数来自 placeholder 按钮自身、外层表单容器、相邻表格、背景表格，或无法证明属于目标表格 root
- **THEN** 系统 MUST NOT 使用该点击前行数触发受控重试
- **AND** 如果点击后目标表格 root 已出现真实可编辑行，当前步骤 MUST 报告成功
- **AND** 如果点击后目标表格 root 仍无真实可编辑行，当前步骤 MUST 失败并输出目标 root 不可靠或未新增的诊断

### Requirement: 可编辑表格 iframe 参照不得以临时内部值提前结束
系统 MUST 在 `editable_table.fill_row` 处理 iframe 式弹出参照时，将目标单元格真实回填和候选参照层真实关闭作为 `target-backfill` 提前结束的共同条件；候选点击后产生的参照字段根内部值不得单独证明字段录入完成。

#### Scenario: 收款人候选已勾选但 iframe 参照仍可见
- **WHEN** DSL 文档为 `收款人信息.收款人全称` 执行 `first_available: true`
- **AND** 运行时已将第一条收款人候选勾选为 checked 或 selected
- **AND** 参照字段根已出现临时内部值，但目标单元格仍显示“请选择”或等价空值
- **AND** 当前页面或子 frame 中仍存在该字段的候选表格以及 `确定/确认/保存` 和 `取消` 动作
- **THEN** 运行时 MUST 将该 iframe 弹出参照判定为仍未关闭
- **AND** 运行时 MUST NOT 记录 `close_action=target-backfill` 后提前返回
- **AND** 运行时 MUST 点击当前前景参照内的确认动作并等待目标单元格真实回填

#### Scenario: 原参照 locator 失效但当前 frame 候选面仍存在
- **WHEN** 候选选择或 frame 重渲染导致最初解析的参照 locator 不可读或失效
- **AND** 当前页面或子 frame 中仍能识别同一业务参照的候选面、确认动作和取消动作
- **THEN** 运行时 MUST 以当前搜索上下文中的可见参照面判定参照仍未关闭
- **AND** 运行时 MUST NOT 仅因旧 locator 不可读而跳过确认动作

#### Scenario: 自动关闭且目标单元格已回填保持成功
- **WHEN** 可编辑表格参照候选点击后候选层真实关闭
- **AND** 目标单元格已经从占位或空值变为可识别业务值
- **THEN** 运行时 SHALL 保持既有 `target-backfill` 成功路径
- **AND** 运行时 MUST NOT 为本修复重复点击背景页面或已关闭参照中的确认动作

### Requirement: 可编辑表格动作消费统一表格作用域
系统 MUST 在执行 `editable_table.add_row` 或 `editable_table.fill_row` 前解析唯一的当前前景可编辑表格作用域。`fill_row` 的全部字段列 MUST 在激活行或单元格前完成预校验；`add_row` SHALL 使用目标表格身份和可见列证据限定新增入口与新增结果验证。

#### Scenario: fill_row 缺少任一字段列时不开始录入
- **WHEN** `editable_table.fill_row` 声明多个字段
- **AND** 已解析目标表格缺少任一字段列或父表头限定无法唯一匹配
- **THEN** 当前步骤 MUST 在激活目标行或首个单元格前失败
- **AND** 系统 MUST NOT 部分录入其它字段

#### Scenario: add_row 只验证目标作用域
- **WHEN** `editable_table.add_row` 已解析当前前景目标表格
- **THEN** 新增入口扫描和行增长验证 MUST 限定到该作用域
- **AND** 背景表格或相邻表格的行变化 MUST NOT 作为新增成功证据

#### Scenario: DOM 根失效时由统一能力受控重试
- **WHEN** 可编辑表格作用域解析后、点击新增入口或激活单元格前发现 DOM 根失效
- **THEN** 系统 SHALL 在未产生页面副作用时重新解析一次
- **AND** 动作 implementation MUST NOT 使用原始表名自行扫描其它表格

### Requirement: 可编辑表格标量参照支持过滤提交重试

系统 SHALL 在 `editable_table.fill_row` 录入标量弹出参照列时复用标量弹出参照的隐式过滤语义：首次输入后候选未收敛时，系统 MUST 主动提交一次过滤并重新解析候选，最终仍只接受唯一业务候选。

#### Scenario: 可编辑表格参照输入后需要提交过滤
- **WHEN** `editable_table.fill_row` 为 `YDFTreeModalSelect` 或等价弹出参照列提供标量值 `102100000177`
- **AND** 参照过滤框已填入该值但页面尚未因输入事件刷新候选
- **AND** 当前候选层仍显示多个银行网点候选
- **THEN** 运行时 MUST 在当前字段参照层内点击搜索图标或按回车提交过滤
- **AND** 运行时 MUST 重新解析当前候选层并选择唯一匹配的业务候选
- **AND** 当前字段完成目标单元格回填后 `editable_table.fill_row` MUST 报告该字段录入成功

#### Scenario: 自动过滤的可编辑表格参照保持快速路径
- **WHEN** `editable_table.fill_row` 输入标量参照值后页面已自动刷新为唯一业务候选
- **THEN** 运行时 MUST 直接按既有候选选择和回填规则完成录入
- **AND** 运行时 MUST NOT 因本需求强制执行一次无必要的重复过滤提交

#### Scenario: 可编辑表格参照提交后仍然歧义
- **WHEN** `editable_table.fill_row` 的标量参照在输入和最多一次提交过滤重试后仍存在两个或更多不同业务候选
- **THEN** 当前字段 MUST 失败并报告候选数量和候选摘要
- **AND** 运行时 MUST NOT 默认选择第一条候选或继续录入同一行的后续字段

### Requirement: 可编辑表格新增复用已解析作用域令牌
系统在 `editable_table.add_row` 执行前已经解析出唯一 `ResolvedTableScope` 时，新增入口点击前后的行状态验证 MUST 优先复用该作用域令牌定位目标根。背景列表、相邻明细表和包含多个表格的外层页面容器 MUST NOT 覆盖有效作用域令牌对应的目标根。

#### Scenario: 有效作用域令牌限定新增行验证
- **WHEN** `editable_table.add_row` 已解析出目标表格作用域令牌
- **AND** 页面同时存在背景列表与目标可编辑表格
- **THEN** 运行时 MUST 在令牌对应根内采集点击前后的真实数据行
- **AND** 步骤报告中的验证根来源 SHALL 表明复用了已解析表格作用域

#### Scenario: 目标表格从一行增长到两行
- **WHEN** 页面业务联动已经在目标表格生成第 1 行
- **AND** DSL 明确执行一次 `editable_table.add_row`
- **THEN** 运行时 MUST 点击目标表格新增入口一次
- **AND** 步骤报告 MUST 记录目标表格真实数据行从 1 行增长到 2 行
- **AND** 系统 MUST NOT 将背景列表行数作为新增成功证据

#### Scenario: 作用域令牌失效时保持失败关闭
- **WHEN** 已解析作用域令牌在新增验证时不再对应唯一可见目标根
- **THEN** 当前步骤 MUST 在点击新增入口前失败
- **AND** 运行时 MUST NOT 按全页身份或行数重新猜测目标根

### Requirement: 可编辑表格单元格回填等待遵守总预算
系统 SHALL 将 `editable_table.fill_row` 的单元格回填检查视为端到端墙钟预算。首次单元格读取、后续读取和轮询暂停 MUST 只使用剩余时间；不可读或失效单元格在预算耗尽后必须按既有未回填语义失败。

#### Scenario: 失效单元格不得落入默认读取超时
- **WHEN** 可编辑表格字段录入后目标单元格不可读、失效或持续未回填
- **AND** 当前回填等待窗口尚有有限剩余时间
- **THEN** 系统 MUST 限制每次单元格读取和轮询使用剩余时间
- **AND** 系统 MUST 在总窗口耗尽后保留既有失败诊断
- **AND** 系统 MUST NOT 因单次读取的浏览器默认超时延长当前字段录入步骤

#### Scenario: 窗口内真实单元格回填保持成功
- **WHEN** 可编辑表格字段录入后目标单元格在总等待窗口内回填为目标值
- **THEN** 系统 MUST 保持既有字段录入成功和字段级诊断语义

### Requirement: 新增行前景表单出现后停止增行轮询
系统 SHALL 在目标表格新增点击后出现新的可交互前景编辑层时停止等待表格即时增行，并继续使用有效动态模板及工作面就绪证据裁决表单模式成功。

#### Scenario: 空表新增打开表单
- **WHEN** `editable_table.add_row` 点击目标表格新增入口后打开可交互行编辑表单
- **AND** 目标表格尚未增加数据行
- **THEN** 系统 MUST NOT 为等待表格增行继续走满行数轮询或额外固定延迟
- **AND** 系统 MUST 等待并验证对应动态模板后才能报告表单已打开

#### Scenario: 非空表新增打开表单不重试点击
- **WHEN** 目标表格已有数据行
- **AND** 新增点击打开了可交互行编辑层但表格行数未变
- **THEN** 系统 MUST NOT 因行数未变而再次点击新增入口

#### Scenario: 前景变化没有模板证据
- **WHEN** 新增点击后出现前景层但没有有效行编辑模板
- **AND** 目标表格也没有真实增行
- **THEN** 系统 MUST 保持新增未生效的失败门禁
- **AND** 系统 MUST NOT 仅凭前景层出现报告新增成功

#### Scenario: 行内模式仍验证真实增行
- **WHEN** 新增点击没有打开新的前景编辑层
- **THEN** 系统 MUST 保持目标表格真实增行验证、有界等待和既有受控重试语义
- **AND** 点击前已存在的前景层 MUST NOT 让本次行数等待提前结束
