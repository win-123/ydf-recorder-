## ADDED Requirements

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
系统 SHALL 识别页脚使用 `保存/取消` 而不是 `确定/确认` 的弹出参照弹窗。

#### Scenario: 识别保存取消结构的弹出参照
- **WHEN** 弹出参照字段打开前景弹窗，弹窗包含参照标题、候选树或表格内容，以及 `保存` 和 `取消` 页脚按钮
- **THEN** 运行时 MUST 将该弹窗解析为当前活动的弹出参照根
- **AND** 运行时 MUST NOT 仅因为弹窗缺少 `确定` 或 `确认` 就失败并提示“未打开弹出参照选择框”

#### Scenario: 使用保存按钮确认弹出参照
- **WHEN** 弹出参照候选行已被选择，且当前可见弹窗页脚包含 `保存`
- **THEN** 运行时 MUST 将 `保存` 作为默认弹出参照确认动作
- **AND** 运行时 MUST 在弹窗根内点击确认按钮，等待弹窗关闭或字段回填，并在结果中报告确认按钮标签

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
