## MODIFIED Requirements

### Requirement: 可编辑表格新增行成功必须验证真实数据行
系统 MUST 在 `editable_table.add_row` 点击新增入口后验证目标可编辑表格出现真实可编辑数据行或打开行编辑表单模板；如果目标表格仍为空态、仍显示 `暂无数据` 或没有可用于后续 `editable_table.fill_row` 的数据行，且没有打开行编辑表单模板，当前新增行步骤 MUST 失败并输出诊断。如果目标表格已有数据行，点击后目标表格真实数据行数量没有增加，且没有打开行编辑表单模板，当前新增行步骤 MUST 失败并输出诊断。

#### Scenario: 点击新增后出现可编辑行才成功
- **WHEN** DSL 文档执行 `editable_table.add_row`
- **AND** 运行时点击了目标表格作用域内的 `新增`
- **AND** 目标表格从空态变为包含真实数据行，例如第一行显示序号 `1`
- **THEN** 当前步骤 MUST 报告成功
- **AND** 步骤结果 SHALL 包含目标表格身份、点击入口诊断和新增后的行状态摘要

#### Scenario: 空表新增打开行编辑表单时成功
- **WHEN** DSL 文档执行 `editable_table.add_row` 并声明 `target.editor: form`
- **AND** 运行时点击了目标表格作用域内的 `新增`
- **AND** 目标表格仍为空态，但当前前景打开了该行的行编辑表单模板
- **THEN** 当前步骤 MUST 报告成功
- **AND** 步骤结果 SHALL 包含目标表格身份、点击入口、点击前后行状态和动态模板摘要
- **AND** 系统 MUST NOT 因主 frame 与 page 指向同一文档而再次点击该新增入口

#### Scenario: 点击后仍是暂无数据时当前步骤失败
- **WHEN** DSL 文档执行 `editable_table.add_row`
- **AND** 运行时点击了某个 `新增` 入口
- **AND** 等待后目标表格仍只包含 `暂无数据` 或没有可编辑数据行
- **AND** 当前前景没有打开行编辑表单模板
- **THEN** 当前步骤 MUST 失败
- **AND** 错误信息 MUST 指向新增行未生效
- **AND** 系统 MUST NOT 将该步骤报告为成功并把失败延迟到后续 `editable_table.fill_row`

#### Scenario: 未指定表格名保持单表兼容
- **WHEN** DSL 文档执行 `editable_table.add_row` 且未提供 `target.table`
- **AND** 当前前景页面只有一个可识别的可编辑表格新增入口
- **THEN** 系统 SHALL 保持既有点击语义
- **AND** 系统 MUST 仍执行新增后的真实数据行或行编辑表单模板校验

#### Scenario: 非空表格点击新增后行数未增长时失败
- **WHEN** DSL 文档执行 `editable_table.add_row`，目标表格为 `需求清单`
- **AND** 点击前目标表格已有 1 条真实数据行
- **AND** 运行时点击了某个 `新增` 入口后没有打开行编辑表单模板
- **AND** 等待后目标表格仍只有 1 条真实数据行
- **THEN** 当前 `editable_table.add_row` 步骤 MUST 失败
- **AND** 错误信息 MUST 指向新增行未生效，并包含点击前后行数摘要
- **AND** 系统 MUST NOT 将该步骤报告为成功并把同一行交给后续 `editable_table.fill_row` 重复维护
