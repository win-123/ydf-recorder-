## ADDED Requirements

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

## MODIFIED Requirements

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
