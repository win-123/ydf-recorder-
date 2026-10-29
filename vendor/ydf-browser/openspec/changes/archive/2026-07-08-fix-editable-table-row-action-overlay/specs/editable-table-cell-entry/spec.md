## MODIFIED Requirements

### Requirement: 可编辑表格单元格激活避开行级动作浮层
系统 MUST 在执行 `editable_table.fill_row` 激活目标单元格时，避开 hover 后覆盖在单元格区域上的行级动作按钮或更多按钮，并点击能够进入编辑态的真实单元格区域。系统 SHALL 在需要临时收起当前行按钮组才能激活目标单元格时，将收起动作限定在当前目标表格和当前目标行，并在字段录入确认后尝试恢复默认行按钮显示行为。

#### Scenario: 行级动作浮层覆盖文本列时仍激活编辑器
- **WHEN** DSL 文档执行 `editable_table.fill_row`，目标表格为 `测算信息`
- **AND** 目标行在 hover 或前序录入后显示 `插入`、`复制`、`删除` 或更多行级动作浮层
- **AND** 字段 `测算依据及说明` 的模板列组件为 `YDFInput`，且目标列身份为 `estDesc`
- **THEN** 运行时 MUST 避开行级动作按钮和更多按钮，激活 `estDesc` 对应的单元格编辑器
- **AND** 运行时 MUST 将 DSL 值录入 `测算依据及说明` 单元格
- **AND** 运行时 MUST NOT 因点击到行级动作浮层而报告 `可编辑表格单元格激活后未出现可输入控件`

#### Scenario: 临时收起当前行按钮后录入并恢复默认行为
- **WHEN** DSL 文档执行 `editable_table.fill_row`，目标表格为 `需求清单`
- **AND** 目标列为 `备注`，目标列身份为 `cgbd_table_remark`
- **AND** 目标行的行级动作按钮组覆盖 `备注` 单元格点击区域
- **AND** 同一目标行行按钮组最右侧存在可收起该按钮组的入口
- **THEN** 运行时 MUST 点击该入口临时收起当前行按钮组
- **AND** 运行时 MUST 重新定位 `cgbd_table_remark` 对应的目标单元格并激活编辑器
- **AND** 运行时 MUST 将 DSL 值录入 `备注` 单元格并确认回填
- **AND** 运行时 SHALL 在回填确认后尝试恢复当前表格当前行的默认行按钮显示行为
- **AND** 运行时 MUST NOT 改变其他表格的行按钮显示状态

#### Scenario: 恢复默认行为失败时保留录入结果和诊断
- **WHEN** `editable_table.fill_row` 已通过临时收起行按钮组完成目标字段录入
- **AND** 目标单元格已确认回填 DSL 值
- **AND** 运行时无法恢复当前行按钮默认显示行为
- **THEN** 当前字段录入结果 SHALL 保留成功回填结果
- **AND** 诊断 SHALL 记录行按钮恢复失败信息
- **AND** 后续字段或后续步骤 MUST 继续基于当前运行时 DOM 重新定位目标，不得复用收起前的旧 locator

#### Scenario: 遮挡无法避开时保留可诊断失败
- **WHEN** 目标单元格被前景浮层或业务控件完全遮挡，运行时无法找到可激活编辑器的点击点
- **THEN** 当前 `editable_table.fill_row` 步骤 MUST 在该字段失败
- **AND** 错误信息 MUST 包含表格名、行号、列名、目标列身份或定位来源
- **AND** 错误信息 SHALL 包含截图路径或等价遮挡诊断，便于区分真实不可编辑列与点击点被遮挡

### Requirement: 可编辑表格新增行成功必须验证真实数据行
系统 MUST 在 `editable_table.add_row` 点击新增入口后验证目标可编辑表格出现真实可编辑数据行；如果目标表格已有数据行，点击后目标表格真实数据行数量没有增加，且没有打开行编辑表单模板，当前新增行步骤 MUST 失败并输出诊断。

#### Scenario: 非空表格点击新增后行数未增长时失败
- **WHEN** DSL 文档执行 `editable_table.add_row`，目标表格为 `需求清单`
- **AND** 点击前目标表格已有 1 条真实数据行
- **AND** 运行时点击了某个 `新增` 入口后没有打开行编辑表单模板
- **AND** 等待后目标表格仍只有 1 条真实数据行
- **THEN** 当前 `editable_table.add_row` 步骤 MUST 失败
- **AND** 错误信息 MUST 指向新增行未生效，并包含点击前后行数摘要
- **AND** 系统 MUST NOT 将该步骤报告为成功并把同一行交给后续 `editable_table.fill_row` 重复维护
