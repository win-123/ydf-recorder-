## ADDED Requirements

### Requirement: 无模板操作框复用表单录入

系统 SHALL 使用现有 `form.fill` 处理前景审批操作框中的固有字段和业务配置增加的简单字段，不要求该框具有单据模板。标签 MUST 关联到真实可交互控件或其唯一字段容器，MUST NOT 因弹窗包含其它可编辑控件就把纯标签视为输入框。字段录入 SHALL 复用对应控件的赋值和回填确认语义，确认或取消 MUST 由后续显式 `dialog` 步骤执行。

#### Scenario: 退回环节按普通下拉选择
- **WHEN** 退回操作框展示“请选择退回环节”标签及对应的普通下拉
- **AND** `form.fill` 为该字段指定 `first_available: true`
- **THEN** 系统 MUST 绑定对应下拉并选择当前第一个可用候选
- **AND** 系统 MUST 确认实际回填值并在报告中保留字段身份与选择结果
- **AND** 系统 MUST NOT 将纯标签当作 `RuntimeInput`

#### Scenario: 扩展简单字段与固有字段共用赋值
- **WHEN** 同一操作框包含业务配置增加的文本或普通下拉字段
- **AND** DSL 在 `target.fields` 中使用其当前可见标签指定目标值
- **THEN** 系统 SHALL 在该前景表单范围内使用现有文本或下拉赋值流程
- **AND** 系统 MUST 确认各字段实际值后才报告成功

#### Scenario: 标签缺少可交互控件
- **WHEN** 操作框中的目标仅有标签，对应控件不存在、不可编辑或不可交互
- **THEN** 系统 MUST 拒绝将该标签作为可录入字段
- **AND** 系统 MUST NOT 将弹窗内其它字段的可编辑状态转移给该标签
