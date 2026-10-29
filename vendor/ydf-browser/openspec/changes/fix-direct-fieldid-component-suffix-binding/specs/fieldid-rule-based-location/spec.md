## MODIFIED Requirements

### Requirement: 规则推导 fieldid 候选
系统 SHALL 基于 YonDiF 单据模板中的直连身份、`dataField`、组件类型和父容器身份，为可定位组件生成运行时 `fieldid` 候选，并在绑定和点击前优先使用这些候选。模板节点已声明自身直连身份时，系统 MUST NOT 使用“父容器 + dataField”约定覆盖该身份。

#### Scenario: 表单字段优先使用节点直接身份
- **WHEN** 模板表单项声明 `divCode=userNameField`、`dataField=userName` 且组件为 `YDFInput`
- **THEN** 系统 MUST 将 `userNameField` 作为平台直接身份候选
- **AND** binder MUST 在文本、placeholder 或宽泛 label 匹配前按 `PRS-FORM-001` 校验该身份的当前运行时状态

#### Scenario: 父容器与 dataField 只是模板约定
- **WHEN** 模板父表单容器 `divCode=detailForm` 且子项只有 `dataField=userName`
- **AND** 平台直接身份不能证明子项 `fieldid=detailForm_userName`
- **THEN** 系统 SHALL 将 `detailForm_userName` 只作为模板命名约定候选
- **AND** 命中该候选的步骤 MUST 报告 `unverified`，MUST NOT 报告平台已验证身份

#### Scenario: 表格列使用平台证明的派生身份
- **WHEN** 表格 `divCode=table1` 且列 `dataField=code`
- **THEN** 系统 MUST 生成 `table1_code` 作为 `PRS-TABLE-001` 的平台后缀身份候选
- **AND** 系统 MUST NOT 将 `table1_table_code` 标记为平台已验证身份

#### Scenario: 精确身份命中但运行状态不合格
- **WHEN** 平台直接身份或已验证后缀身份唯一命中隐藏、disabled、readOnly、背景或不可接收 pointer 的组件
- **THEN** 当前操作 MUST 失败并保留身份与状态证据
- **AND** runtime MUST NOT 改选文本、placeholder 或标签相似的组件

#### Scenario: 精确身份不可用时有界降级
- **WHEN** 平台基线、组件变体或运行时 DOM 无法提供可用的直接身份或已验证后缀身份
- **THEN** 系统 SHALL 进入 `unverified` 有界兼容路径并报告稳定 `fallback_reason`
- **AND** 只有当前作用域内运行时证据唯一且安全时才能成功

#### Scenario: 根据父容器 divCode 和 dataField 生成表单字段候选
- **WHEN** 模板中存在父表单容器 `divCode=detailForm`，其子表单项 `dataField=userName` 且组件为 `YDFInput`
- **AND** 该子表单项没有自身 `fieldid` 或 `divCode`
- **THEN** 系统 MUST 生成运行时身份候选 `detailForm_userName`
- **AND** binder MUST 在文本、placeholder 或宽泛 label 匹配前优先尝试该身份候选

#### Scenario: 节点自身直连身份优先于父容器约定
- **WHEN** 表单项没有自身 `fieldid` 但声明了 `divCode=setModeInp`
- **AND** 其父表单容器为 `divCode=pay_form`，字段为 `dataField=setModeCode`
- **THEN** 系统 MUST 将 `setModeInp` 作为平台直连身份候选
- **AND** 系统 MUST 保留 `pay_form_setModeCode` 作为模板命名约定候选
- **AND** binder MUST NOT 用 `pay_form_setModeCode` 覆盖平台直连身份的精确校验结果

#### Scenario: 直连身份生成组件后缀族
- **WHEN** 平台直连身份为 `setModeInp`，且组件为 `YDFSelect` 或 `YDFTreeSelect`
- **THEN** 系统 MUST 生成 `setModeInp_input`、`setModeInp_suffix` 和 `setModeInp_search_input` 作为同一直连身份的后代控件候选
- **AND** 系统 MUST 按模板原文保留身份的大小写

#### Scenario: 直连身份生成日期组件后缀族
- **WHEN** 平台直连身份为 `2025042916094932627680310720055`，且组件为 `YDFDatePicker`
- **THEN** 系统 MUST 生成该直连身份的 `_input` 和 `_suffix` 后代控件候选
- **AND** 系统 MUST 保留“父容器 + dataField”命名约定候选用于有界降级

#### Scenario: 大小写漂移不得破坏直连后缀定位
- **WHEN** 模板 `dataField=manaFeeExtrCode` 但平台直连身份为 `mb_form_manafeeExtrCode`
- **AND** 运行时真实输入为 `mb_form_manafeeExtrCode_search_input`
- **THEN** 系统 MUST 使用 `mb_form_manafeeExtrCode_search_input` 作为精确后代控件候选
- **AND** 系统 MUST NOT 通过大小写无关匹配把该输入误归到 `mb_form_manaFeeExtrCode` 命名约定下

#### Scenario: 同根唯一真实输入可以收敛绑定
- **WHEN** 平台直连身份命中的外层元素与一个可见、可编辑、可接收 pointer 的 `_search_input` 后代位于同一逻辑根
- **AND** 该逻辑根内不存在第二个合格的真实输入控件
- **THEN** binder SHALL 将外层精确身份收敛到该唯一后代输入
- **AND** 绑定结果 MUST 继续携带平台直连身份契约路径

#### Scenario: 只读日期输入通过可点击容器绑定
- **WHEN** `YDFDatePicker` 的直连身份外层容器可见且可接收 pointer
- **AND** 同一逻辑根内只有唯一 readonly 日期 input
- **THEN** binder SHALL 将同根多个外层容器收敛为最内层可点击容器
- **AND** runtime MUST 通过该容器定位内部日期 input 完成写入并确认真实回填

#### Scenario: 多个合格真实输入保持身份歧义
- **WHEN** 同一平台直连身份逻辑根内存在两个或更多可见、可编辑、可接收 pointer 的真实输入控件
- **THEN** binder MUST 保持平台精确身份状态不兼容
- **AND** 系统 MUST NOT 按 DOM 顺序、文本相似度或大小写归一化结果任选其一

#### Scenario: 规则候选不得绕过运行时校验
- **WHEN** 规则推导出的 `fieldid` 在 DOM 中存在多个候选或存在隐藏副本
- **THEN** runtime MUST 继续执行可见性、前景层、可编辑性、动作文本和 pointer event 可达性校验
- **AND** runtime MUST NOT 仅因规则候选命中就返回成功
