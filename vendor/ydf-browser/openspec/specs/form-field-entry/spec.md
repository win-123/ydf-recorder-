# form-field-entry Specification

## Purpose
定义普通表单字段在 `form.fill` 中的前景层绑定、背景字段排除和写后确认语义，确保弹窗、抽屉或动态表单中的字段不会被背景同名字段误填。

## Requirements

### Requirement: 前景表单字段绑定
系统 SHALL 在 `form.fill` 录入普通表单字段时优先绑定当前前景弹窗、抽屉或动态表单中的可见、可编辑、可接收 pointer 的字段，避免同名或同 `fieldid` 的背景及旧前景字段被误填。

#### Scenario: 前景弹窗字段优先于背景同 fieldid 字段
- **WHEN** 页面打开新增表单后，背景页和前景表单同时存在 `dataField=proCode` 或 `fieldid=proCode` 的字段
- **AND** DSL 执行 `form.fill` 填写 `项目代码`
- **THEN** runtime MUST 选择前景表单中可见、可编辑、非表格的 `项目代码` 控件
- **AND** runtime MUST NOT 将背景页、详情区或列表区的同名字段作为录入目标

#### Scenario: 同 fieldid 前景实例优先可接收 pointer 的控件
- **WHEN** 动态抽屉切换后同时存在多个可见、同 `fieldid=proName` 的 `项目名称` 输入
- **AND** 旧抽屉输入不可接收 pointer，当前抽屉输入可接收 pointer
- **THEN** runtime MUST 选择当前抽屉中可接收 pointer 的输入
- **AND** runtime MUST NOT 因旧实例在 DOM 中更靠前或已标记 `in_dialog=true` 而向旧实例录入

#### Scenario: 前景字段按标签或身份匹配
- **WHEN** 前景表单字段没有稳定 `fieldid`，但其 `label_text`、`aria_label`、`placeholder`、`dataField` 或模板 key 能匹配 DSL 字段名
- **THEN** runtime MUST 允许该前景字段作为 `form.fill` 目标
- **AND** runtime MUST 在存在多个候选时优先选择可编辑字段而不是只读展示字段

#### Scenario: 同名展示字段不得抢占可编辑参照字段
- **WHEN** 前景动态表单中同时存在两个标签均为 `采购品目` 的字段
- **AND** 其中一个候选是 `props.disabled=1` 的 `YDFInput` 展示字段
- **AND** 另一个候选是可编辑的 `YDFTableModalSelect` 或 `dataType=refer` 字段
- **AND** DSL 执行 `form.fill`，为 `采购品目` 提供包含 `filter` 和 `match` 的结构化参照目标
- **THEN** runtime MUST 选择可编辑参照字段作为录入目标
- **AND** runtime MUST NOT 将 disabled 展示字段作为当前 `form.fill` 的候选
- **AND** runtime MUST NOT 把结构化参照目标交给普通 choice/dropdown 选择逻辑

### Requirement: 表单字段录入确认
系统 SHALL 在普通表单字段录入后确认目标控件真实回填了 DSL 目标值；未确认时该字段录入 MUST 失败。

#### Scenario: 文本字段未回填时失败
- **WHEN** DSL 执行 `form.fill` 填写普通文本字段
- **AND** runtime 已向目标控件发送输入事件
- **AND** 目标控件在短等待内仍读不到 DSL 目标值
- **THEN** `form.fill` MUST 失败
- **AND** 失败诊断 MUST 包含字段名、目标值、实际读数和运行时 selector

#### Scenario: 年份日期字段确认写入
- **WHEN** DSL 执行 `form.fill` 填写 `YDFDatePicker` 年份字段，例如 `设立年度: "2026"`
- **THEN** runtime MUST 以该字段的真实可编辑控件为目标写入年份
- **AND** runtime MUST 确认字段可见值或 input value 等价于 `2026`

#### Scenario: 成功报告包含确认后的字段
- **WHEN** `form.fill` 完成多个字段录入
- **THEN** 步骤结果 MUST 只把已经确认回填的普通字段报告为成功录入
- **AND** 报告 MUST 包含每个字段的 `fieldid` 或等价运行时身份，便于诊断绑定位置

### Requirement: 参照型选择字段使用弹出参照语义
系统 SHALL 在 `form.fill` 处理表单字段时优先尊重模板 raw 元数据中的 `refuri` 参照声明，即使组件名是 `YDFSelect`，也不能仅因包含 `Select` 而归类为普通 choice 字段。

#### Scenario: YDFSelect 参照元数据打开弹出参照
- **WHEN** DSL 执行 `form.fill` 填写 `结算方式: "1 电子转账支付"`
- **AND** 当前模板字段组件名为 `YDFSelect`
- **AND** 字段 raw 元数据包含非空 `refuri` 参照定义
- **THEN** runtime MUST 将该字段作为 popup reference 字段处理
- **AND** runtime MUST NOT 把该字段交给普通 choice/dropdown 候选选择流程

### Requirement: 表单字段可见值已匹配时保持幂等
系统 SHALL 在 `form.fill` 打开普通 choice 或 popup reference 候选前，先检查当前字段可见值是否已经等价于 DSL 目标值；若已匹配，则该字段录入 MUST 成功且不得重复打开候选层。

#### Scenario: 默认参照选择值已经匹配
- **WHEN** DSL 执行 `form.fill` 填写 `结算方式: "1 电子转账支付"`
- **AND** 当前字段可见值已经是 `1 电子转账支付`
- **THEN** runtime MUST 将该字段录入判定为成功
- **AND** runtime MUST NOT 再打开普通下拉或 popup reference 候选

### Requirement: 表单绑定排除串错 label_text 候选
系统 SHALL 在 `form.fill` 绑定表单字段时识别运行时标签串扰；当候选 runtime 元素只通过 `label_text` 匹配 DSL 字段名，但其自身可见文本、`name` 或等价字段身份明确指向另一个字段时，绑定结果 MUST NOT 选择该候选。

#### Scenario: 收款人全称不绑定到开户银行
- **WHEN** 模板字段 `收款人全称` 需要绑定可编辑表单控件
- **AND** runtime 中存在一个可见可编辑候选，其自身文本为 `开户银行`，但 `label_text` 被错误采集为 `收款人全称`
- **THEN** 绑定逻辑 MUST NOT 将该 `开户银行` 候选作为 `收款人全称` 的录入目标
- **AND** `form.fill` MUST 继续选择其它身份更一致的 `收款人全称` 候选，或在没有可靠候选时失败并报告未绑定字段

#### Scenario: 前景优先不得覆盖字段身份冲突
- **WHEN** 前景弹窗或抽屉中存在只靠 `label_text` 命中的候选
- **AND** 该候选自身文本或字段名与 DSL 字段名归一化后不一致
- **AND** 背景或同层存在自身文本、`fieldid`、模板 key、`dataField`、`aria_label` 或 `placeholder` 更明确匹配 DSL 字段名的候选
- **THEN** 绑定逻辑 MUST 优先选择字段身份一致的候选
- **AND** 绑定逻辑 MUST NOT 仅因为错误候选位于前景层就覆盖字段身份一致的候选

### Requirement: 表单字段绑定使用规则推导身份
系统 SHALL 在 `form.fill` 绑定普通表单字段时，优先使用 YonDiF `父容器 divCode + "_" + dataField` 及组件子控件后缀规则生成的运行时 `fieldid` 候选。

#### Scenario: 普通输入字段使用父容器规则定位
- **WHEN** 模板中 `YDFInput` 字段标签为 `项目名称`，`dataField=proName`，所属表单容器 `divCode=baseForm`
- **THEN** binder MUST 优先尝试运行时身份 `baseForm_proName`
- **AND** 如果该候选可见、可编辑且位于当前前景表单，`form.fill` MUST 使用该候选录入

#### Scenario: 参照字段使用子控件后缀定位
- **WHEN** 模板中表单字段组件为 `YDFTableModalSelect` 或 `YDFTreeModalSelect`
- **AND** 字段 `dataField=depart`，所属表单容器 `divCode=baseForm`
- **THEN** runtime MUST 可使用 `baseForm_depart_input`、`baseForm_depart_btn`、`baseForm_depart_table`、`baseForm_depart_tree`、`baseForm_depart_modal_ok` 和 `baseForm_depart_modal_cancel` 定位参照输入、按钮、弹层和确认动作
- **AND** runtime MUST 继续按现有参照选择语义确认回填值

### Requirement: 日期范围字段录入
系统 SHALL 在 `form.fill` 中支持 `YDFDateRange` 日期范围字段，并将标量区间值解释为开始日期和结束日期的业务范围录入。

#### Scenario: 标量日期范围写法录入
- **WHEN** DSL 执行 `form.fill` 填写 `YDFDateRange` 字段，值为 `2026-01-01~2026-01-12`
- **THEN** runtime MUST 将该值解析为开始日期 `2026-01-01` 和结束日期 `2026-01-12`
- **AND** runtime MUST 真实录入日期范围控件的内部状态
- **AND** runtime MUST NOT 仅向外层字段根节点写入 `value` 或 `title` 后判定成功

#### Scenario: 日期范围分隔符允许空格
- **WHEN** DSL 执行 `form.fill` 填写 `YDFDateRange` 字段，值为 `2026-01-01 ~ 2026-01-12`
- **THEN** runtime MUST 接受该写法
- **AND** runtime MUST 在报告中将实际区间值归一化为 `2026-01-01~2026-01-12`

#### Scenario: 日期范围真实确认
- **WHEN** runtime 完成 `YDFDateRange` 字段录入
- **THEN** runtime MUST 从真实可见值、真实 input value、组件内部可读值或业务保存结果确认该字段已回填
- **AND** 如果只能读回外层字段根节点上由 runtime 自行写入的属性，`form.fill` MUST 失败
- **AND** 失败诊断 MUST 包含字段名、目标区间值、实际读数和运行时 selector 或字段身份

#### Scenario: 对账起止日期保存不再报必填
- **WHEN** 用例填写 `对账起止日期: "2026-01-01~2026-01-12"` 并执行保存
- **THEN** runtime MUST 证明保存流程不再因为 `对账起止日期` 为空而失败
- **AND** 报告 MUST 保留该字段的归一化实际值和确认信息

### Requirement: 视口外表单控件 pointer 状态保持未知
系统在扫描具有平台精确身份的可见、可编辑表单控件时，若控件仅因当前滚动位置完全位于浏览器视口或可恢复的滚动区域之外，pointer 可达性 MUST 记录为未知，不得记录为确定不可达。系统 MUST 依据实际定位包含块判断哪些祖先参与裁剪，并将轴对齐缩放后的边界统一到视口坐标；不可恢复的裁剪与真实遮挡 MUST 保持不可达。未知状态 SHALL 只允许唯一精确身份或同一逻辑根内唯一真实输入以未验证契约绑定。实际文本录入 MUST 由浏览器滚动并完成真实点击校验后执行；点击失败不得继续强制赋值或报告字段已确认。部分可见控件 SHALL 仅在有效可见交集内判断命中；该规则 MUST 覆盖主页面及子 frame。

#### Scenario: 视口外唯一 textarea 保持可录入
- **WHEN** 动态新增表单中的 `YDFTextArea` 具有唯一平台精确身份并且当前完全位于视口外
- **AND** 该控件可见、可编辑、未禁用且未只读
- **THEN** DOM 扫描 MUST 将其 pointer 可达性记录为未知
- **AND** `form.fill` SHALL 以未验证契约绑定该唯一真实 textarea，并由浏览器滚动后录入

#### Scenario: 滚动容器外字段不因固定底栏失去绑定
- **WHEN** 唯一可编辑输入仍与窗口相交，但完全位于可滚动祖先内容可见区域之外
- **AND** 对应窗口坐标命中固定底栏或其它区域
- **THEN** 系统 MUST 将该输入的 pointer 可达性记录为未知
- **AND** `form.fill` SHALL 滚动对应容器后录入并确认实际值

#### Scenario: 部分可见控件仅在有效区域判断命中
- **WHEN** 输入仅部分位于可滚动祖先的内容可见区域中，其余部分被裁剪
- **THEN** 系统 MUST 在有效可见交集内判断 pointer 命中
- **AND** 系统 MUST NOT 用裁剪区域内的固定操作区命中否定输入的可达性

#### Scenario: 视口内被遮挡控件继续失败关闭
- **WHEN** 同一平台精确身份存在有效可见区域内候选，但目标点被其它前景元素遮挡或控件明确设置 `pointer-events: none`
- **THEN** DOM 扫描 MUST 将该候选记录为确定不可接收 pointer
- **AND** 系统 MUST NOT 因视口外未知状态规则将该候选绑定为录入目标

#### Scenario: 不可滚动裁剪不视为滚动位置未知
- **WHEN** 输入被内层 `overflow: hidden/clip` 祖先完全裁剪，且没有内部可恢复的 `auto/scroll` 滚动口
- **AND** 外层即使存在滚动区域也无法改变输入相对该裁剪口的位置
- **THEN** 系统 MUST 将输入判为不可达，MUST NOT 将这种裁剪视为可通过外层滚动恢复的未知 pointer 状态

#### Scenario: 内层滚动可恢复外层裁剪范围
- **WHEN** 外层具有 `overflow: hidden/clip`，但内层滚动区域可以将输入移入其可见交集
- **THEN** 系统 MUST 保持该输入的滚动恢复能力，不得仅因外层裁剪当前隐藏输入而拒绝绑定

#### Scenario: 定位控件按实际包含块判断遮挡
- **WHEN** 固定或绝对定位输入的包含块位于普通 DOM 滚动祖先之外
- **THEN** 系统 MUST NOT 使用该普通祖先的滚动口裁剪输入
- **AND** 输入在实际可见区域被覆盖时 MUST 保持不可达
- **AND** 存在参与裁剪的定位包含块时 MUST 继续考虑该包含块的裁剪

#### Scenario: 缩放后的滚动边界保持一致
- **WHEN** 表单滚动区域存在轴对齐 CSS 缩放或 `zoom`
- **THEN** 系统 MUST 将边框、滚动口与输入矩形换算到同一视口坐标
- **AND** 离开有效可见区域的可恢复输入 MUST 保持未知，实际可见但被覆盖的输入 MUST 保持不可达

#### Scenario: 滚动后被遮挡的文本不得强制写入
- **WHEN** 输入因离屏未知状态获得唯一绑定，但实际滚动后的点击被其它元素拦截
- **THEN** 文本录入 MUST 失败，MUST NOT 继续通过强制填值或 DOM 赋值写入目标
- **AND** 输入值与输入事件 MUST 保持未被该次录入修改

#### Scenario: 点击成功后的键盘录入仍支持兜底
- **WHEN** 目标文本输入已通过真实点击校验，但键盘录入方式失败
- **THEN** 系统 SHALL 保留现有文本填写兜底并继续确认实际值

#### Scenario: 视口外同根多输入保持不兼容
- **WHEN** 同一平台精确身份逻辑根内存在两个或更多可见、可编辑的真实输入
- **AND** 这些输入当前均位于浏览器视口或可滚动祖先内容可见区域之外
- **THEN** 系统 MUST 保持平台精确身份状态不兼容
- **AND** 系统 MUST NOT 仅因 pointer 状态未知而选择 DOM 顺序中的第一个输入

### Requirement: 普通文本域不得由弱参照装饰改写语义
系统 SHALL 将没有明确参照组件身份或模板 `refuri` 等参照元数据的 `YDFTextArea` 作为普通文本字段处理；祖先容器中的搜索、箭头、选择或相似视觉装饰 MUST NOT 单独使文本域进入弹出参照流程。

#### Scenario: 带搜索装饰的备注仍按文本录入
- **WHEN** DSL 执行 `form.fill` 填写 `YDFTextArea` 字段 `备注`
- **AND** 该字段没有明确参照组件身份或模板参照元数据
- **AND** 字段祖先容器中存在搜索、箭头或选择装饰
- **THEN** 系统 MUST 按普通文本录入并确认字段回填
- **AND** 系统 MUST NOT 打开弹出参照候选层

#### Scenario: 明确参照文本域保持参照语义
- **WHEN** DSL 执行 `form.fill` 填写 `YDFTextArea` 字段
- **AND** 该字段模板具有明确参照组件身份或非空 `refuri` 参照元数据
- **THEN** 系统 MUST 保持既有弹出参照选择和回填确认语义

### Requirement: 可输入页面参照支持标量文本录入

系统 SHALL 在 `form.fill` 处理 `YDFReferSelect` 时，对 `props.referType` 为 `uidata` 或 `link` 且 `props.caninput` 明确开启的字段，将标量目标作为自由文本录入；系统 MUST 在失焦后确认实际值，不能要求文本已存在于参照候选中。

#### Scenario: 新摘要不依赖已有候选
- **WHEN** 表单中的页面参照允许自由输入，DSL 为其提供新的标量字符串
- **THEN** 系统 MUST 录入该字符串并在失焦后确认实际值
- **AND** 系统 MUST NOT 打开参照弹窗要求选择已有候选

#### Scenario: 结构化目标继续选择参照
- **WHEN** 同一可输入字段收到 `first_available`、`match` 或其它结构化参照目标
- **THEN** 系统 MUST 使用既有参照选择及回填确认流程

#### Scenario: 非自由输入参照保持原有语义
- **WHEN** 字段未明确开启 `caninput`、不属于页面参照模式，或组件为树参照或表格参照
- **THEN** 系统 MUST 保持既有候选选择和回填要求

#### Scenario: 失焦后未保留输入值时失败
- **WHEN** 自由文本已输入，但失焦后实际值与目标值不一致
- **THEN** 系统 MUST 将字段录入判定为失败并报告实际值

### Requirement: 无模板操作框复用表单录入

系统 SHALL 使用现有 `form.fill` 处理前景审批操作框中的固有字段和业务配置增加的简单字段，不要求该框具有单据模板。标签 MUST 关联到真实可交互控件或其唯一字段容器，MUST NOT 因弹窗包含其它可编辑控件就把纯标签视为输入框。字段录入 SHALL 复用对应控件的赋值和回填确认语义，确认或取消 MUST 由后续显式 `dialog` 步骤执行。

#### Scenario: 退回环节按普通下拉选择
- **WHEN** 退回操作框展示“请选择退回环节”标签及对应的普通下拉
- **AND** `form.fill` 为该字段指定 `first_available: true`
- **THEN** 系统 MUST 绑定对应下拉并选择当前第一个可用候选
- **AND** 系统 MUST 确认实际回填值并在报告中保留字段身份与选择结果
- **AND** 系统 MUST NOT 将纯标签当作 `RuntimeInput`

#### Scenario: 扩展简单字段与固有字段共用赋值
- **WHEN** 同一操作框包含业务配置增加的文本或普通下拉字段
- **AND** DSL 在 `target.fields` 中使用其当前可见标签指定目标值
- **THEN** 系统 SHALL 在该前景表单范围内使用现有文本或下拉赋值流程
- **AND** 系统 MUST 确认各字段实际值后才报告成功

#### Scenario: 标签缺少可交互控件
- **WHEN** 操作框中的目标仅有标签，对应控件不存在、不可编辑或不可交互
- **THEN** 系统 MUST 拒绝将该标签作为可录入字段
- **AND** 系统 MUST NOT 将弹窗内其它字段的可编辑状态转移给该标签
