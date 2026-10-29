# popup-reference-row-selection-state Specification

## Purpose
定义弹出参照表格行选择的选中态判定、当前弹窗范围约束和主子表顺序选择语义，确保 YonDiF WUI 表格行只在行根呈现 `selected` 时也能被稳定识别为已选择。
## Requirements
### Requirement: 弹出参照表格行支持行级选中态
系统 SHALL 在弹出参照表格候选行选择后，将候选行根上的明确选中态作为有效选择结果。

#### Scenario: row_number 选择接受行级 selected
- **WHEN** `popup_reference.select` 目标使用 `selections[].row_number` 选择弹出参照表格行
- **AND** 真实点击后该行根包含 `selected` class 或 `aria-selected=true`
- **AND** 行内 radio 或 checkbox input 的 `checked` 仍为 `false`
- **THEN** runtime MUST 判定该行已成功选中
- **AND** runtime MUST NOT 抛出 `未找到弹出参照第 N 行`

#### Scenario: 控件 checked 仍保持兼容
- **WHEN** 弹出参照表格行点击后行内 radio 或 checkbox 呈现 `checked=true`、`aria-checked=true` 或 checked class
- **THEN** runtime MUST 继续按既有控件选中态判定为成功
- **AND** 行级 selected 判断 MUST NOT 破坏既有控件选中场景

### Requirement: 弹出参照行选中态必须限定在当前弹窗表格行
系统 MUST 只在当前弹出参照候选表格行范围内判断行级选中态，避免背景页或固定列副本干扰。

#### Scenario: 不使用背景页面行状态
- **WHEN** 前景弹出参照和背景页面都包含表格行
- **THEN** runtime MUST 只检查当前弹出参照根内、当前选择目标所属表格行的选中态
- **AND** 背景页面中的 `selected`、`active` 或 checked 状态 MUST NOT 让弹出参照选择误报成功

#### Scenario: 固定列副本和主体行保持一致判断
- **WHEN** WUI 表格为固定列和主体列渲染同一业务行的多个 DOM 副本
- **AND** 真实点击左侧固定列 radio 后，选中态只体现在同一业务行的某个行根副本上
- **THEN** runtime MUST 能够按当前弹窗表格范围内的同一行索引或等效行根确认该业务行已选中
- **AND** runtime MUST NOT 因点击目标自身 input 未 checked 而判定失败

### Requirement: 主子表弹出参照顺序选择保持联动
系统 SHALL 支持弹出参照 `selections` 中先选择主表行、等待子表加载，再选择子表行。

#### Scenario: 选择项目预算主表后预算编制科目加载
- **WHEN** 用例打开 `选择项目预算` 弹窗并执行 `popup_reference.select`
- **AND** 目标 `selections` 先选择 `table: 项目预算` 的 `row_number: 1`
- **THEN** runtime MUST 点击主表行并接受行级 selected 作为主表选择成功
- **AND** runtime MUST 等待下方 `预算编制科目` 子表从 `暂无数据` 更新为可选择行后，再处理下一条 selection

#### Scenario: 子表行选择后确认弹窗
- **WHEN** `selections` 已成功选择 `项目预算` 主表行
- **AND** 下一条 selection 选择 `table: 预算编制科目` 的行
- **THEN** runtime MUST 在子表范围内选择对应行
- **AND** runtime MUST 点击弹窗确认按钮并在步骤结果中报告两个 selection 均已处理

### Requirement: first_available 候选选择控件必须真实选中
系统 SHALL 在弹出参照 `first_available` 选择中识别候选项、候选行或候选树节点内的可见选择控件，并且在选择控件真实选中后才报告候选选择成功。

#### Scenario: YDFTreeModalSelect 候选 checkbox 在确认前被勾选
- **WHEN** `form.fill` 为 `YDFTreeModalSelect` 字段提供 `filter` 和 `first_available: true`
- **AND** 过滤后的第一个可用候选显示为轻量列表或树节点，例如 `A01 北京总仓`
- **AND** 该候选文本前存在可见且未禁用的 checkbox
- **THEN** runtime MUST 点击该 checkbox 或其可交互包装节点
- **AND** runtime MUST 在确认弹窗前验证该候选已呈现 checked、aria checked/selected、或明确 selected/checked 状态
- **AND** runtime MUST NOT 仅因候选文本行视觉高亮就报告选择成功

#### Scenario: 未勾选的 first_available 候选不能被接受
- **WHEN** `first_available` 候选包含可见 checkbox 或 radio
- **AND** runtime 点击候选文本、候选行和选择控件后仍无法读取到有效选中态
- **THEN** runtime MUST 继续尝试同一候选集合中的下一个可选择候选
- **AND** 如果没有候选能进入有效选中态，runtime MUST 失败并保留 first available 候选诊断
- **AND** runtime MUST NOT 点击确认按钮后把页面提示 `请选择数据！` 误报为字段已录入

#### Scenario: 无选择控件的候选保持兼容
- **WHEN** `first_available` 候选范围内的第一个可用候选没有可见 checkbox 或 radio
- **THEN** runtime SHALL 保持既有候选点击、自动关闭或字段回填判定行为
- **AND** runtime MUST NOT 要求这类候选额外呈现 checked 状态

### Requirement: first_available 参照字段已有值时保持幂等
系统 SHALL 在弹出参照 `first_available` 候选已成功选中后，允许表单字段已有非空可见值且确认后保持同值的场景判定为成功。

#### Scenario: first_available 选择已有同值字段
- **WHEN** `form.fill` 为表格型弹出参照字段提供 `first_available: true`
- **AND** runtime 已找到候选并确认候选呈现 checked、aria checked/selected、或明确 selected/checked 状态
- **AND** 字段选择前已有非空可见值
- **AND** 点击确认后字段可见值仍为同一个非空值
- **THEN** runtime MUST 判定该字段录入成功
- **AND** runtime MUST NOT 抛出 `弹出参照选择未回填到字段`

#### Scenario: first_available 无字段值仍失败
- **WHEN** `form.fill` 为弹出参照字段提供 `first_available: true`
- **AND** 候选选择或确认后目标字段仍读不到任何非空可见值
- **THEN** runtime MUST 继续按回填失败处理
- **AND** runtime MUST 保留诊断截图或候选诊断信息

### Requirement: 匹配候选存在选择控件时必须验证真实选中态
系统 MUST 在标量值或 `match` 选择命中的弹出参照候选包含可见 checkbox/radio 时，确认该选择控件真实进入选中态后才报告选择成功。

#### Scenario: 标量短值命中带 checkbox 的唯一候选
- **WHEN** `form.fill` 的标量值 `二级采购项目` 唯一命中候选 `360000241010010000008 二级采购项目`
- **AND** 候选行前存在可见且未禁用的 checkbox
- **THEN** 运行时 MUST 点击 checkbox 或其可交互包装节点
- **AND** 运行时 MUST 在确认弹窗前验证 checkbox 呈现 `checked=true`、`aria-checked=true` 或明确 checked 状态

#### Scenario: 行高亮不能替代 checkbox 选中
- **WHEN** 标量值或 `match` 命中的候选行获得焦点、蓝色高亮、`active` 或宽泛行级 `selected` 状态
- **AND** 候选内可见 checkbox/radio 仍未选中
- **THEN** 运行时 MUST NOT 将该候选判定为业务选择成功
- **AND** 运行时 MUST 继续尝试点击真实选择控件，仍无法选中时失败并保留诊断

#### Scenario: 结构化 match 复用相同选择态要求
- **WHEN** `form.fill` 或 `popup_reference.select` 使用 `match.equals` 或 `match.contains` 命中带 checkbox/radio 的候选
- **THEN** 运行时 MUST 复用与标量值相同的选择控件点击和选中态验证规则
- **AND** 运行时 MUST NOT 在只完成文本匹配或行点击后直接返回成功

#### Scenario: 无选择控件候选保持兼容
- **WHEN** 标量值或 `match` 命中的候选没有可见 checkbox/radio
- **THEN** 运行时 SHALL 继续使用既有候选点击、字段回填或弹窗关闭判定
- **AND** 运行时 MUST NOT 要求该候选产生不存在的 checked 状态

### Requirement: first_available 必须忽略空状态候选
系统 MUST 在弹出参照 `first_available` 候选发现中排除空状态、表头、分页、查询区、footer 和普通说明文本；这些节点不得作为右侧候选表格的数据行被点击或报告为已尝试业务候选。

#### Scenario: 空状态和真实业务行同时存在
- **WHEN** 弹出参照当前根内同时存在隐藏或非目标区域的 `暂无数据`、`暂时没有数据` 空状态文本，以及可见商品表格业务行
- **AND** DSL 使用 `first_available: true`
- **THEN** runtime MUST 忽略空状态候选
- **AND** runtime MUST 将可见商品业务行作为第一条可用候选尝试选择
- **AND** runtime MUST NOT 只尝试空状态候选后报告 `未找到弹出参照可选值`

#### Scenario: 只有空状态时保留失败诊断
- **WHEN** 弹出参照当前根内没有任何有效业务候选行、树节点或列表项
- **AND** 只存在 `暂无数据`、`暂时没有数据` 或等价空状态文本
- **THEN** runtime MUST 让 `first_available` 选择失败
- **AND** 失败诊断 SHALL 说明当前没有有效候选，并保留空状态摘要或截图

### Requirement: first_available 可见表格行必须按业务行选择
系统 MUST 将可见表格中的第一条有效业务数据行识别为 `first_available` 的右表候选，并在该行包含 radio 或 checkbox 时验证真实选中态。

#### Scenario: 商品参照只有一条可见业务行
- **WHEN** `YDFTableModalSelect` 商品参照弹窗显示一条业务行，例如 `0702154531736 / 商品_0702154531736`
- **AND** 该行左侧存在可见且未禁用的 radio
- **AND** DSL 使用 `first_available: true`
- **THEN** runtime MUST 点击该业务行的 radio 或等价可交互包装节点
- **AND** runtime MUST 验证该行、radio 或等价选择控件进入 checked、selected 或 aria checked/selected 状态
- **AND** runtime MUST NOT 将查询框、表头、分页、footer 或空状态文本作为最终候选

#### Scenario: 业务行可见但未能选中时失败
- **WHEN** `first_available` 已识别出可见业务表格行
- **AND** runtime 点击该行或其选择控件后仍无法读取有效选中态
- **THEN** runtime MUST 继续尝试同一有效候选集合中的下一个业务候选
- **AND** 如果没有候选能进入有效选中态，runtime MUST 失败并保留候选文本、候选来源、是否要求选择态和截图路径
