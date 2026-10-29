## ADDED Requirements

### Requirement: 连续参照结束后恢复父明细模板
系统 SHALL 在独立参照默认确认后应用已就绪的下一参照模板；连续临时参照全部退出后，系统 MUST 根据运行时身份和可见性恢复重新可操作的父表单，不要求 DSL 提供 `restore_previous` 或运行时表格 fieldid。

#### Scenario: 新增明细后连续选择三个参照
- **WHEN** `editable_table.add_row` 打开项目参照
- **AND** 三次独立 `popup_reference.select` 使用默认确认依次选择项目、指标和费用
- **AND** 最后确认后父表单重新可操作，临时参照身份均不再可操作
- **THEN** 系统 MUST 恢复父表单 manifest 并重新绑定
- **AND** 后续 `editable_table.fill_row` MUST 可按父表单中的明细表名称录入
- **AND** 最后确认步骤 MUST 记录 `restored_template` 和 `auto_restored_template: true`

#### Scenario: 中间参照保持活动上下文
- **WHEN** 一次确认后下一参照已打开并有已就绪的模板响应
- **THEN** 系统 MUST 应用下一参照模板
- **AND** 系统 MUST NOT 因父表单背景动作可见而提前退出当前参照链

#### Scenario: 恢复证据不足或未确认时保留当前模板
- **WHEN** 本次选择没有确认，或当前参照仍活跃，或父模板没有更强的运行时证据
- **THEN** 系统 MUST 保留当前模板和历史栈
