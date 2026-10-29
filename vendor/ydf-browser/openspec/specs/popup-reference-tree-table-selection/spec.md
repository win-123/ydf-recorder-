# popup-reference-tree-table-selection Specification

## Purpose
描述 `YDFReferSelect` 等弹出参照字段的树表选择语义，包括在前景参照弹窗内限定左侧树上下文、按右侧表格候选行规则选择值、使用 `保存` 类页脚动作确认，以及让独立 `popup_reference.select` 复用同一套树表参照行为。

## Requirements

### Requirement: 表单字段支持树表弹出参照选择
系统 SHALL 允许 `form.fill` 的弹出参照字段值声明可选的参照弹窗内树上下文，以及右侧表格候选行选择规则。

#### Scenario: 通过弹窗内树和表格匹配选择项目负责人
- **WHEN** 用例将 `项目负责人` 填写为包含 `tree.label: 101 综合司01` 和 `match.column: 人员名称` 的结构化值
- **THEN** 运行时 MUST 打开该字段的弹出参照，解析当前可见的参照弹窗根，在该弹窗根内选择 `101 综合司01`，再按 `人员名称` 匹配右侧人员表格行，勾选行选择控件，确认弹窗，并等待字段回填
- **AND** 步骤结果 MUST 记录参照弹窗内树上下文和被选中的表格匹配信息

#### Scenario: 在弹窗树上下文下选择第一条可用候选
- **WHEN** 用例将弹出参照字段填写为包含 `tree` 和 `first_available: true` 的结构化值
- **THEN** 运行时 MUST 先应用参照弹窗内树上下文
- **AND** 运行时 MUST 在该树上下文下选择第一个可用的候选行或候选项，确认弹窗，并等待字段回填

#### Scenario: 弹窗树上下文不能作为最终选择值
- **WHEN** 用例将弹出参照字段填写为包含 `tree` 但不包含 `match`、`matches`、`row_number`、`row_numbers`、`first_available` 或 `selections` 的结构化值
- **THEN** DSL 校验 MUST 在业务步骤执行前失败
- **AND** 错误信息 MUST 说明弹窗内 `tree` 只用于限定参照候选范围，不能作为最终字段值

### Requirement: 弹出参照目标结构支持树上下文
系统 MUST 在 `form.fill` 结构化字段值和 `popup_reference.select` 目标中校验包含 `tree` 或 `trees` 的弹出参照目标。

#### Scenario: 接受树目标简写
- **WHEN** 弹出参照目标包含 `tree: 101 综合司01` 和有效的 `match`
- **THEN** DSL 校验 MUST 接受该目标，并将树简写解释为按标签匹配的弹窗内树目标

#### Scenario: 接受树目标对象写法
- **WHEN** 弹出参照目标包含 `tree.label`、`tree.value`、`tree.node` 或 `tree.name`，并同时包含有效的最终行选择目标
- **THEN** DSL 校验 MUST 接受该目标，并保留这些树字段供运行时在弹窗根内限定选择

#### Scenario: 拒绝不安全的树选择器目标
- **WHEN** 弹出参照目标的 `tree` 包含裸 DOM selector 字段
- **THEN** DSL 校验 MUST 在业务步骤执行前失败
- **AND** 错误信息 MUST 引导作者使用语义化树标签、值或快捷节点

### Requirement: 弹出参照识别支持保存确认
系统 SHALL 识别页脚使用 `保存/取消` 而不是 `确定/确认` 的弹出参照弹窗，并且在参照前景层仍可见时不得跳过确认动作。

#### Scenario: 识别保存取消结构的弹出参照
- **WHEN** 弹出参照字段打开前景弹窗，弹窗包含参照标题、候选树或表格内容，以及 `保存` 和 `取消` 页脚按钮
- **THEN** 运行时 MUST 将该弹窗解析为当前活动的弹出参照根
- **AND** 运行时 MUST NOT 仅因为弹窗缺少 `确定` 或 `确认` 就失败并提示“未打开弹出参照选择框”

#### Scenario: 使用保存按钮确认弹出参照
- **WHEN** 弹出参照候选行已被选择，且当前可见弹窗页脚包含 `保存`
- **THEN** 运行时 MUST 将 `保存` 作为默认弹出参照确认动作
- **AND** 运行时 MUST 在弹窗根内点击确认按钮，等待弹窗关闭或字段回填，并在结果中报告确认按钮标签

#### Scenario: iframe 参照仍可见时不得提前返回
- **WHEN** `form.fill` 已在 `PM_SELECT_MANAGER` 这类 iframe 式弹出参照中选中目标候选
- **AND** 当前页面或子 frame 中仍存在可见的参照候选树或表格，以及同一前景参照内的 `保存` 和 `取消` 页脚按钮
- **THEN** 运行时 MUST 判定该弹出参照仍未关闭
- **AND** 运行时 MUST NOT 以 `confirmed=false` 提前返回
- **AND** 运行时 MUST 点击该前景参照内的 `保存`，等待参照关闭或字段回填，并在步骤结果中报告 `confirmed=true` 和 `confirm_label=保存`

#### Scenario: 显式确认按钮标签覆盖默认值
- **WHEN** 弹出参照目标声明 `confirm_label`
- **THEN** 运行时 MUST 在弹窗根内优先使用该标签作为确认动作
- **AND** 运行时 MUST 仍然要求命中的元素是可见的弹窗页脚动作

### Requirement: 结构化参照分流不影响普通下拉
系统 MUST 将 `YDFReferSelect` 或 `dataType=refer` 字段的结构化弹出参照目标分流到弹出参照流程，同时不改变标量下拉字段行为。

#### Scenario: 结构化参照目标进入弹窗流程
- **WHEN** 字段绑定为 `YDFReferSelect` 或 `dataType=refer`，且字段值是包含 `tree`、`match`、`matches`、`row_number`、`row_numbers`、`first_available` 或 `selections` 的对象
- **THEN** 运行时 MUST 打开参照弹窗并使用弹出参照选择语义
- **AND** 运行时 MUST NOT 将该对象字符串化，也不能把它交给普通下拉 choice 选择逻辑

#### Scenario: 标量普通下拉行为保持不变
- **WHEN** 非参照 `YDFSelect` 或普通下拉字段填写标量值
- **THEN** 运行时 SHALL 继续使用已有 choice/dropdown 选择行为
- **AND** 弹出参照树表逻辑 MUST NOT 作用于该字段

#### Scenario: 既有表格和树形弹窗参照保持兼容
- **WHEN** 字段已按 `YDFTableModalSelect` 或 `YDFTreeModalSelect` 处理，并使用既有 `match` 或 `value` 目标结构
- **THEN** 运行时 MUST 保持已有选择行为，除非目标显式使用新的弹出参照树上下文

### Requirement: 独立弹出参照选择复用树表语义
系统 SHALL 在独立 `popup_reference.select` 步骤中支持与 `form.fill` 相同的树表参照目标语义。

#### Scenario: 在已打开的弹出参照中选择
- **WHEN** 用例在参照弹窗已可见时执行 `popup_reference.select`，且目标包含 `tree` 和 `match`
- **THEN** 运行时 MUST 解析当前弹窗根，应用参照弹窗内树上下文，匹配并选择候选行，并按 `form.fill` 使用的同一规则确认弹窗

#### Scenario: 选择序列可以包含弹窗树上下文
- **WHEN** `popup_reference.select` 目标使用 `selections`，且某个选择项包含 `tree` 和行目标
- **THEN** 运行时 MUST 在处理该选择项的行目标前先应用对应树上下文
- **AND** 每个选择项 MUST 始终限定在当前弹窗根内

### Requirement: 弹出参照表格匹配支持 contains
系统 SHALL 在 `form.fill` 结构化弹出参照目标和独立 `popup_reference.select` 目标中支持 `match.contains`，并将其作为表格候选行的包含匹配目标。

#### Scenario: 独立弹出参照按 contains 选择表格候选
- **WHEN** 用例在已打开的弹出参照中执行 `popup_reference.select`，且 `target.match.column` 为 `用户名称`、`target.match.contains` 为 `财会`
- **AND** 当前弹窗表格中存在 `用户名称` 单元格文本包含 `财会` 的候选行，例如 `财会监督1`
- **THEN** 运行时 MUST 在当前弹窗根内选择该候选行
- **AND** 运行时 MUST 按当前弹出参照确认规则点击确认按钮或等待弹窗关闭

#### Scenario: 表单结构化参照按 contains 选择表格候选
- **WHEN** `form.fill` 的弹出参照字段值包含 `match.column` 和 `match.contains`
- **AND** 参照弹窗过滤后存在目标列文本包含该值的候选行
- **THEN** 运行时 MUST 复用弹出参照表格匹配规则选择该候选行
- **AND** 步骤结果 MUST 记录被选中的 `match` 结构，且不得把目标对象字符串化为普通文本录入

#### Scenario: contains 失败诊断保留目标值
- **WHEN** 弹出参照目标使用 `match.contains` 但当前弹窗表格没有任何候选行匹配
- **THEN** 运行时 MUST 失败并保留弹窗诊断
- **AND** 诊断中的表格匹配调试信息 MUST 将 `wantedValue` 设置为 `match.contains` 的值，而不是空字符串

### Requirement: 前景业务弹窗内支持嵌套弹出参照字段
系统 SHALL 支持在前景业务弹窗、抽屉或 iframe 表单中通过 `form.fill` 填写 `YDFReferSelect` 等弹出参照字段，并将外层业务表单与内层候选参照选择框区分为不同上下文。

#### Scenario: 设置经费管理员弹窗内选择人员参照
- **WHEN** DSL 点击工具栏 `设置经费管理员` 后打开前景业务弹窗
- **AND** 前景业务弹窗内存在字段 `经费管理员`，字段模板组件为 `YDFReferSelect` 或等价弹出参照字段
- **AND** DSL 执行 `form.fill`，为 `经费管理员` 提供 `filter.conditions.field: 人员名称` 和 `match.column: 人员名称`
- **THEN** runtime MUST 在当前前景业务弹窗表单中定位 `经费管理员` 字段
- **AND** runtime MUST 点击该字段自身的参照触发控件打开内层人员候选参照
- **AND** runtime MUST 在内层候选参照中按 `人员名称` 查询和匹配候选行
- **AND** runtime MUST NOT 直接在外层业务弹窗中查找 `人员名称` 查询字段

#### Scenario: 外层业务表单不被当作候选参照根
- **WHEN** 当前可见前景层包含普通表单字段、附件区域以及 `确认/取消` 或 `保存/取消` 页脚动作
- **AND** 该前景层没有可选择的候选表格、候选树、候选列表或等价候选选择面
- **THEN** runtime MUST NOT 将该前景层解析为弹出参照候选根
- **AND** runtime MUST 继续等待或查找由目标字段触发后出现的内层候选参照根
- **AND** 如果内层候选参照未出现，错误诊断 MUST 保留外层前景层文本和 frame URL 或等价上下文信息

#### Scenario: 内层参照选择后恢复外层弹窗上下文
- **WHEN** runtime 已在内层候选参照中选中目标候选并确认
- **AND** 外层业务弹窗仍然可见
- **THEN** runtime MUST 将 `form.fill` 结果记录为对应字段已选择，并保留内层参照选择结果
- **AND** runtime MUST 保持外层业务弹窗作为当前前景表单上下文
- **AND** 后续 `toolbar.click`、`dialog.confirm` 或继续 `form.fill` MUST 作用于外层业务弹窗，而不是已关闭的内层参照根或背景列表页

#### Scenario: 页面级直接弹出参照保持兼容
- **WHEN** 页面表单字段直接打开候选树表参照，不经过外层业务弹窗
- **THEN** runtime SHALL 继续使用既有弹出参照树表选择语义
- **AND** 新增前景业务弹窗上下文识别 MUST NOT 要求 DSL 增加 selector、frame、层级或弹窗类型字段

### Requirement: 候选参照根不得误用外层业务表单或背景页面
系统 MUST 将弹出参照候选根限定为真实候选选择层，并与背景页面、外层业务表单、业务助手、普通内容卡片和已关闭旧弹层区分开。

#### Scenario: 背景编辑页不是候选参照根
- **WHEN** 当前页面是单据新增或编辑页
- **AND** 页面中包含表格、树、`保存/取消` 页脚按钮或业务说明文本
- **AND** 目标字段触发后没有出现新的候选参照表格、候选树、候选列表或等价选择面
- **THEN** 运行时 MUST NOT 将该背景编辑页解析为弹出参照候选根
- **AND** 运行时 MUST 继续等待目标字段候选层，或在超时后报告当前字段候选参照未打开

#### Scenario: 外层业务弹窗不被复用为内层候选参照
- **WHEN** 当前可见前景层是业务表单弹窗、抽屉或 iframe
- **AND** 该前景层包含普通表单字段、附件区域、说明区或业务按钮
- **AND** 目标字段是该前景层内的 `YDFReferSelect` 或等价弹出参照字段
- **THEN** 运行时 MUST 点击目标字段自身触发内层候选参照
- **AND** 运行时 MUST NOT 仅因外层业务表单包含 `保存/取消`、表格或可见文本就将其复用为候选参照根

#### Scenario: 旧弹层上下文不参与新字段候选选择
- **WHEN** 上一个 `popup_reference.select` 或字段参照已经确认并关闭
- **AND** 后续步骤为另一个字段打开新的弹出参照
- **THEN** 运行时 MUST 重新解析当前字段的候选参照根
- **AND** 运行时 MUST NOT 复用上一个字段的已关闭弹层、旧 marker 或旧 choice root
- **AND** 如果新的候选参照没有出现，运行时 MUST 失败在新字段的弹层解析阶段

### Requirement: 弹层复用必须验证候选选择面有效
系统 SHALL 允许复用已打开的弹出参照层，但复用前 MUST 验证该层是当前可用候选选择面。

#### Scenario: 复用已打开候选参照
- **WHEN** DSL 当前步骤在一个已经可见的候选参照层内继续执行选择
- **AND** 该候选层包含可见候选表格数据行、候选树节点、候选列表项或等价选择控件
- **THEN** 运行时 SHALL 复用该候选层
- **AND** 运行时 SHALL 在该候选层内执行 `filter`、`first_available`、`match`、`row_number` 或 `selections`

#### Scenario: 复用候选层不破坏嵌套参照
- **WHEN** 前景业务弹窗内的字段打开内层候选参照
- **AND** 外层业务弹窗和内层候选参照同时可见
- **THEN** 运行时 MUST 将内层候选参照作为候选根
- **AND** 运行时 MUST 保持内层参照选择成功后恢复外层业务弹窗上下文的既有行为
- **AND** 运行时 MUST NOT 为修复可编辑表格回归而禁止合法的内层候选参照复用

### Requirement: 弹出参照打开优先点击真实触发按钮
系统 MUST 在打开弹出参照字段时，将字段根内的真实参照触发按钮优先于搜索输入容器、组合框输入区或其他仅负责聚焦输入的容器。

#### Scenario: 参照按钮和搜索容器同在字段根内
- **WHEN** 弹出参照字段根内同时存在 `show-search` 或 `combobox` 搜索输入容器，以及带 `button`、`modal-btn`、`wui-button`、`icon-only` 或 `*_btn` 身份的参照触发按钮
- **THEN** 运行时 MUST 优先点击参照触发按钮
- **AND** 运行时 MUST NOT 仅因为搜索输入容器的右边界或面积排序更靠前就点击该容器

#### Scenario: 缺少明确按钮身份时保留几何兜底
- **WHEN** 弹出参照字段根内没有明确的按钮标签、按钮角色、按钮 class 或按钮 fieldid
- **THEN** 运行时 SHALL 继续使用候选元素的右边界和面积排序作为兜底
- **AND** 运行时 MUST 保持既有可打开参照字段的兼容行为

### Requirement: 弹出参照打开失败诊断保留触发排序依据
系统 SHALL 在启用弹出参照诊断模式时记录打开阶段的候选触发控件、实际点击目标、弹窗计数、网络增量和候选排序依据。

#### Scenario: 诊断报告包含实际点击目标
- **WHEN** 环境变量启用弹出参照诊断模式，并且弹出参照打开后没有出现可用候选弹窗
- **THEN** 运行时 MUST 输出诊断 JSON
- **AND** 诊断 JSON MUST 包含实际点击目标的标签、class、fieldid、位置、pointer 命中信息和来源

#### Scenario: 诊断候选包含排序权重
- **WHEN** 环境变量启用弹出参照诊断模式，并且字段根内存在多个触发候选
- **THEN** 诊断 JSON SHALL 在候选列表中记录每个可见候选的排序权重
- **AND** 候选列表 SHALL 按运行时实际使用的排序规则排列，便于判断是否点中了错误元素

### Requirement: 标量弹出参照值必须唯一确定单个候选

系统 SHALL 将 `form.fill` 和独立 `popup_reference.select` 的标量弹出参照值解释为单目标选择，并在标量隐式过滤后的当前有效候选范围内只接受唯一业务候选。若首次输入过滤值后候选仍未收敛，系统 MUST 在最终唯一性判定前最多主动提交一次过滤并重新解析候选。

#### Scenario: 标量短值过滤出唯一候选
- **WHEN** `form.fill` 为弹出参照字段填写标量值 `二级采购项目`
- **AND** 运行时使用该值过滤后只有业务候选 `360000241010010000008 二级采购项目`
- **THEN** 运行时 MUST 选择该唯一候选并按当前参照确认规则完成字段回填
- **AND** 运行时 MUST NOT 要求 DSL 为唯一候选补充完整代码前缀

#### Scenario: 标量隐式过滤需要主动提交后才收敛
- **WHEN** `form.fill` 或 `popup_reference.select` 为弹出参照字段提供标量值
- **AND** 输入过滤值后当前候选层仍包含两个或更多候选，且页面要求点击搜索图标或按回车才触发过滤
- **THEN** 运行时 MUST 在最终唯一性判定前使用当前候选层内已有的搜索图标或回车动作提交过滤
- **AND** 运行时 MUST 等待候选层稳定后重新解析当前前景候选根并再次按标量值匹配
- **AND** 运行时 MUST 最多执行一次该隐式过滤提交重试

#### Scenario: 标量完整文本命中层级结果中的叶子候选
- **WHEN** 标量弹出参照值完整等于当前候选层中的一个叶子文本
- **AND** 当前候选层同时展示该叶子对应的银行、地区或根节点层级文本
- **THEN** 运行时 MUST 优先选择与标量值精确相等的叶子候选
- **AND** 运行时 MUST NOT 仅因这些层级文本同时可见而报告歧义

#### Scenario: 树候选路径文本和叶子文本指向同一业务候选
- **WHEN** `form.fill` 为树形弹出参照字段填写标量值 `30101 基本工资`
- **AND** 运行时使用该值过滤后同时看到树路径候选 `301 工资福利支出 30101 基本工资` 和叶子候选 `30101 基本工资`
- **THEN** 运行时 MUST 在唯一性判断前将该路径候选和叶子候选合并为同一个业务候选
- **AND** 运行时 MUST 优先选择可验证的叶子候选并按当前参照确认规则完成字段回填
- **AND** 运行时 MUST NOT 仅因祖先路径文本和叶子文本同时存在而报告多候选歧义

#### Scenario: 候选点击后字段已回填且候选弹层消失
- **WHEN** 标量树形弹出参照候选点击后，运行时未能从候选节点读取到 checked 或 selected 状态
- **AND** 目标字段已经回填为匹配标量目标的值
- **AND** 当前候选弹层已经关闭或候选选择面已经消失
- **THEN** 运行时 MUST 判定该候选选择已完成
- **AND** 运行时 MUST NOT 在字段已经回填且候选层已经消失后继续提交过滤、二次查找候选或报告 `无可见下拉/参照候选`

#### Scenario: 候选节点关闭后选中态验证不得长时间等待
- **WHEN** 标量树形弹出参照候选点击后导致候选弹层关闭或候选 DOM 节点失效
- **AND** 运行时尝试读取候选 checked 或 selected 状态
- **THEN** 运行时 MUST 使用短超时完成该状态读取
- **AND** 运行时 MUST NOT 因失效候选节点触发浏览器默认长超时等待

#### Scenario: 候选弹层隐藏判断不得长时间等待
- **WHEN** 标量树形弹出参照候选点击后，运行时需要判断候选弹层或候选选择面是否已经隐藏
- **THEN** 运行时 MUST 使用短超时完成弹层可见候选面检查
- **AND** 运行时 MUST NOT 因失效弹层节点或跨 frame 候选面扫描触发浏览器默认长超时等待

#### Scenario: 标量唯一候选失败后不得继续旧式兜底查找
- **WHEN** 标量弹出参照唯一候选路径已经尝试点击当前候选
- **AND** 已完成最多一次隐式过滤提交重试，或当前目标不满足该重试条件
- **AND** 该候选路径返回未选中或未验证成功
- **THEN** 运行时 MUST 立即返回给外层字段回填和弹层隐藏检查
- **AND** 运行时 MUST NOT 在同一次候选点击和受控提交重试后继续执行列表、树展开、树节点点击或表格行点击等旧式兜底查找

#### Scenario: 标量短值过滤出多个候选
- **WHEN** `form.fill` 或 `popup_reference.select` 的标量弹出参照值在隐式过滤和最多一次提交重试后仍过滤出两个或更多不同业务候选
- **THEN** 运行时 MUST 失败并报告匹配候选数量
- **AND** 运行时 MUST NOT 默认选择第一条或勾选全部候选
- **AND** 错误信息 MUST 提示使用更完整的值、`first_available`、`row_number`、列表或 `selections` 明确选择意图

#### Scenario: 同一业务行的 DOM 副本不构成歧义
- **WHEN** 当前弹出参照因固定列、虚拟滚动或布局结构为同一业务候选渲染多个 DOM 行副本
- **THEN** 运行时 MUST 在唯一性判断前合并同一业务候选副本
- **AND** 运行时 MUST NOT 仅因 DOM 副本数量大于一而报告多候选歧义

#### Scenario: 显式位置选择不受唯一性约束
- **WHEN** 弹出参照目标显式使用 `first_available` 或 `row_number`
- **THEN** 运行时 SHALL 按既有位置选择语义选择候选
- **AND** 标量值的唯一性要求 MUST NOT 改变该显式行为

#### Scenario: 显式多选不受单目标约束
- **WHEN** 弹出参照字段使用列表、`values` 或 `selections` 表达多个目标
- **THEN** 运行时 SHALL 按既有多选语义处理每个显式目标
- **AND** 运行时 MUST NOT 将整个多选目标集合按标量唯一性规则拒绝

### Requirement: 普通表单弹出参照必须确认完成
系统 SHALL 在 `form.fill` 处理普通表单弹出参照字段时，将候选选择、确认动作、字段回填和候选层关闭作为同一个字段录入完成条件；仅记录 `selected` 但 `confirmed=false` 的结果 MUST NOT 被视为字段录入成功。

#### Scenario: 人员参照未确认不得通过
- **WHEN** `form.fill` 为 `项目联系人` 或 `项目负责人` 这类 `YDFReferSelect` 普通表单字段提供 `filter.conditions.field: 人员名称` 和 `match.column: 人员名称`
- **AND** runtime 已匹配或点击目标候选，并在步骤结果中记录 `selected`
- **AND** runtime 未能确认弹出参照关闭或字段真实回填，导致参照结果为 `confirmed=false`
- **THEN** 当前 `form.fill` 字段录入 MUST 失败
- **AND** 用例整体 MUST NOT 报告 `passed`
- **AND** 失败诊断 MUST 包含字段名、候选目标和未确认关闭或未回填的原因

#### Scenario: 人员参照确认关闭后通过
- **WHEN** `form.fill` 为 `项目联系人` 或 `项目负责人` 选择人员候选
- **AND** runtime 点击当前前景参照内的 `保存`、`确定`、`确认` 或等价确认动作
- **AND** runtime 证明候选参照层已关闭且字段值已回填为目标人员
- **THEN** 当前字段录入 MUST 成功
- **AND** 步骤结果 MUST 包含 `selected`、`confirmed=true`，并在可读时包含 `confirm_label`

#### Scenario: 自动关闭参照必须证明回填
- **WHEN** 普通表单弹出参照在点击候选后自动关闭
- **THEN** runtime MUST 在返回成功前确认目标字段可见值、隐藏值或等价字段状态已回填目标候选
- **AND** runtime MUST 确认当前页面和相关 frame 中不再存在该字段打开的候选参照层
- **AND** 如果任一确认失败，当前字段录入 MUST 失败

### Requirement: 弹出参照早退只允许有后续回填校验的路径
系统 MUST 将候选点击后跳过确认按钮的早退语义限制在有独立后续回填校验的路径中，例如可编辑表格单元格参照；普通表单 `form.fill` 字段不得复用该早退作为成功条件。

#### Scenario: 普通表单不复用可编辑表格早退
- **WHEN** 普通表单弹出参照候选点击后未读到候选选中态
- **AND** runtime 的快速状态判断认为候选面可能已关闭
- **THEN** runtime MUST 继续尝试当前参照的确认动作或执行普通表单字段回填校验
- **AND** runtime MUST NOT 仅以 `selected` 和 `confirmed=false` 返回成功

#### Scenario: 可编辑表格保留外层回填兜底
- **WHEN** `editable_table.fill_row` 的参照单元格候选点击后候选层关闭但候选选中态不可读
- **THEN** runtime SHALL 允许将控制权返回给可编辑表格单元格回填等待逻辑
- **AND** 该单元格回填等待 MUST 仍然负责最终判定成功或失败
- **AND** 普通表单字段成功条件 MUST NOT 因该兜底而放宽

### Requirement: 弹出参照未确认诊断可追踪
系统 SHALL 在 `form.fill` 弹出参照字段未确认完成时保留可追踪诊断，帮助区分候选未命中、确认按钮未点击、候选层仍可见、候选层误判隐藏和字段未回填。

#### Scenario: 报告保留未确认原因
- **WHEN** 普通表单弹出参照字段失败于未确认完成
- **THEN** 错误信息或步骤诊断 MUST 包含字段名和目标选择结构
- **AND** 诊断 SHOULD 包含 `close_action`、字段回填检测结果、候选层可见性判断或确认按钮标签中的至少一种

#### Scenario: 成功报告保留确认路径
- **WHEN** 普通表单弹出参照字段确认完成
- **THEN** 步骤结果 MUST 记录该字段的 `confirmed=true`
- **AND** 如果 runtime 点击了确认动作，步骤结果 MUST 在可读时记录 `confirm_label`
- **AND** 如果 runtime 通过自动关闭和回填证明成功，步骤结果 MUST 记录等价的关闭或回填证据

### Requirement: 弹出参照根回填等待遵守总预算
系统 SHALL 将弹出参照确认后的字段根回填等待视为端到端墙钟预算。首次读取、后续 DOM 读取和轮询暂停 MUST 只使用该预算的剩余时间，且超时后必须沿用既有未回填失败语义。

#### Scenario: 失效字段根不得放大回填窗口
- **WHEN** 弹出参照确认后目标字段根不可读、失效或持续未回填
- **AND** 当前回填等待窗口尚有有限剩余时间
- **THEN** 系统 MUST 将每次读取和轮询限制在剩余时间内
- **AND** 系统 MUST 在总窗口耗尽后报告既有未回填失败
- **AND** 系统 MUST NOT 因单次读取使用浏览器默认长超时而延长该窗口

#### Scenario: 窗口内真实回填保持成功
- **WHEN** 弹出参照确认后目标字段根在总等待窗口内回填为目标值
- **THEN** 系统 MUST 保持既有确认成功语义

### Requirement: 探索与测试 DSL 分离
系统 MUST 保持测试 DSL 不变，不提供 popup_reference.discover 操作。未开启探索参数时 MUST NOT 主动展开参照。

#### Scenario: 观察当前已渲染候选
- **WHEN** 用户仅开启 --ai-observe
- **THEN** 页面摘要 MUST 提供当前前景参照的有界候选、路径、结构末级和可选性证据
- **AND** 采集 MUST NOT 展开、过滤、选择或确认参照

#### Scenario: 显式末尾探索
- **WHEN** 用户配合 --ai-observe 指定 --explore-reference JSON 且用例成功结束
- **THEN** 系统 MUST 只对当前已经打开的前景参照执行有界路径展开或过滤
- **AND** 系统 MUST NOT 选择、确认、保存或重放业务步骤
- **AND** 探索状态 MUST 单独写入末步 data.reference_exploration，不改变原测试结果

#### Scenario: 用例失败或没有打开参照
- **WHEN** 用例执行失败或结束时没有参照
- **THEN** 系统 MUST 分别报告探索跳过或探索失败
- **AND** 系统 MUST NOT 自动打开其它业务页面

#### Scenario: 参数与覆盖范围
- **WHEN** 路径不是最多 32 个非空文本、offset 为负数、limit 不在 1 到 500、包含未知字段或未开启观察
- **THEN** CLI MUST 在执行前拒绝该探索参数
- **WHEN** 返回已渲染候选
- **THEN** 系统 MUST 明确报告范围、截断和继续发现方式，不将报告分页解释为后台全集分页

#### Scenario: 候选表格的隐藏和敏感内容
- **WHEN** 当前参照表格包含隐藏单元格或具有敏感身份的可见单元格
- **THEN** 候选证据 MUST 排除隐藏内容，并对敏感单元格脱敏
- **AND** 行文本和路径 MUST NOT 保留敏感内容副本

### Requirement: 参照选择拒绝保留真实原因
系统 MUST 在当前参照选择收到新的警告或错误拒绝通知时保留该原因、目标与通知，不得只报告弹窗未关闭。

#### Scenario: 选择父节点被末级规则拒绝
- **WHEN** 当前选择或确认触发请选择末级节点的拒绝通知
- **THEN** 当前步骤 MUST 失败并在主错误中保留该消息
- **AND** 结构化证据 MUST 包含选择目标与拒绝通知
- **AND** 系统 MUST NOT 自动更换业务候选

#### Scenario: 旧通知不属于本次拒绝
- **WHEN** 参照开始选择前已有警告且当前选择成功回填
- **THEN** 系统 MUST NOT 将旧警告归因于本次参照选择

#### Scenario: 新拒绝与旧提示文案相同
- **WHEN** 当前选择产生新的通知节点，其警告文案与选择开始前的提示相同
- **THEN** 系统 MUST 将新通知保留为本次拒绝
- **AND** 原有节点因无关页面变更被重新扫描时 MUST NOT 被认作新拒绝

### Requirement: 连续参照确认按原选择面的前景状态判定完成
独立 `popup_reference.select` 默认确认后，系统 SHALL 判定本次选择的参照是否已退出前景交互；若新的独立参照已接管交互，旧参照保留在后台 MUST NOT 导致本次选择失败。系统 MUST 保留原参照仍可交互、通知拒绝和证据不足时的失败行为。

#### Scenario: 确认项目后立即打开指标参照
- **WHEN** 本次参照已选中目标并点击确定
- **AND** 新的独立参照成为前景可交互工作面，原参照已隐藏或被其覆盖
- **THEN** 本次选择 MUST 返回 `confirmed=true`
- **AND** 系统 MUST NOT 点击下一参照的确定或重试原参照确认
- **AND** 后续选择 MUST 可按下一参照标题继续执行

#### Scenario: 原参照确认后仍然活跃
- **WHEN** 确认后原参照仍作为前景候选选择面可交互
- **THEN** 系统 MUST 继续等待或失败
- **AND** 系统 MUST NOT 因页面存在另一个背景参照就报告完成

#### Scenario: 字段参照仍要求真实回填
- **WHEN** 表单、查询或可编辑表格字段参照确认后切换选择面
- **THEN** 原入口的字段回填校验 MUST 保留
- **AND** 前景切换 MUST NOT 替代字段值确认

### Requirement: 参照树优先搜索并限制展开候选
系统 SHALL 在前景参照存在可用树搜索框且目标节点尚不可点击时先搜索，再在搜索未命中时有界展开。展开 MUST 排除叶子占位图标，并且重叠绑定规则不得反复尝试同一不可展开节点。

#### Scenario: 搜索命中后直接选择目标
- **WHEN** 参照目标声明 `tree.label`，且当前参照有可用树搜索框
- **THEN** 系统 MUST 在逐层展开前搜索目标并保留精确节点匹配
- **AND** 搜索命中时 MUST 直接选择目标，不遍历无关分支

#### Scenario: 搜索不可用时有界展开
- **WHEN** 搜索框不存在或搜索未命中目标
- **THEN** 系统 MUST 保留有界展开回退
- **AND** 搜索未命中时 MUST 恢复搜索前的过滤值，再执行展开回退
- **AND** 叶子、禁用、已展开节点 MUST NOT 作为折叠展开按钮
- **AND** 同一失败候选 MUST NOT 因多个绑定规则重叠而重复等待

#### Scenario: 树上下文仍须完成右表行选择
- **WHEN** 目标包含 `tree` 和 `first_available: true`
- **THEN** 搜索或展开成功后系统 MUST 继续按既有规则选择右表候选、确认参照并验证回填
