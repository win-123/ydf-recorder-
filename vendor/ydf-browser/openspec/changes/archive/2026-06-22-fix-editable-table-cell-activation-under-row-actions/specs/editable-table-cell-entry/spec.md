## ADDED Requirements

### Requirement: 可编辑表格单元格激活避开行级动作浮层
系统 MUST 在执行 `editable_table.fill_row` 激活目标单元格时，避开 hover 后覆盖在单元格区域上的行级动作按钮或更多按钮，并点击能够进入编辑态的真实单元格区域。

#### Scenario: 行级动作浮层覆盖文本列时仍激活编辑器
- **WHEN** DSL 文档执行 `editable_table.fill_row`，目标表格为 `测算信息`
- **AND** 目标行在 hover 或前序录入后显示 `插入`、`复制`、`删除` 或更多行级动作浮层
- **AND** 字段 `测算依据及说明` 的模板列组件为 `YDFInput`，且目标列身份为 `estDesc`
- **THEN** 运行时 MUST 避开行级动作按钮和更多按钮，激活 `estDesc` 对应的单元格编辑器
- **AND** 运行时 MUST 将 DSL 值录入 `测算依据及说明` 单元格
- **AND** 运行时 MUST NOT 因点击到行级动作浮层而报告 `可编辑表格单元格激活后未出现可输入控件`

#### Scenario: 遮挡无法避开时保留可诊断失败
- **WHEN** 目标单元格被前景浮层或业务控件完全遮挡，运行时无法找到可激活编辑器的点击点
- **THEN** 当前 `editable_table.fill_row` 步骤 MUST 在该字段失败
- **AND** 错误信息 MUST 包含表格名、行号、列名、目标列身份或定位来源
- **AND** 错误信息 SHALL 包含截图路径或等价遮挡诊断，便于区分真实不可编辑列与点击点被遮挡
