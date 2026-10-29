## ADDED Requirements

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
