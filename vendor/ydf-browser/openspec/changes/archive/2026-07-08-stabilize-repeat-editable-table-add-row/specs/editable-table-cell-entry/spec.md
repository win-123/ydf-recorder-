## ADDED Requirements

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
