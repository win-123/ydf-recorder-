## ADDED Requirements

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
