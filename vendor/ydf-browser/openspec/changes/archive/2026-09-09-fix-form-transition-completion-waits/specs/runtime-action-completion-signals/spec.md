## ADDED Requirements

### Requirement: 点击源工作面关闭及时完成等待
系统 SHALL 将本次实际点击元素关联到精确源工作面，在该工作面已关闭且返回区域存在可交互控件时，以 `foreground_closed` 结束通用动作等待，再执行原有模板恢复校验。

#### Scenario: 行编辑表单确定关闭
- **WHEN** `toolbar.click` 点击前景行编辑表单中的确定按钮
- **AND** 该按钮所属的精确工作面关闭且返回区域已可交互
- **THEN** 系统 MUST 以 `foreground_closed` 结束等待而不是等满兼容超时
- **AND** 系统 MUST 继续按实际状态恢复和绑定父模板

#### Scenario: 同一入口的弹窗和普通动作
- **WHEN** `dialog.click` 或 `action.click` 通过共享点击入口关闭精确编辑工作面
- **AND** 返回区域已可交互
- **THEN** 系统 MUST 使用与工具栏动作相同的关闭完成规则

#### Scenario: 工作面仍可见或发生无关变化
- **WHEN** 本次点击的源工作面仍然活跃，或只发生其他工作面关闭、标题变化及背景刷新
- **THEN** 系统 MUST NOT 使用 `foreground_closed` 提前结束等待

### Requirement: 新确认框就绪只交接确认动作
系统 SHALL 在本次点击所在工作面或其祖先文档出现新的唯一标准确认框，且确认动作已可交互时，以 `confirmation_required` 结束当前点击等待。该信号 MUST NOT 表示保存、提交或其他业务动作成功。

#### Scenario: 保存确认框先于保存请求
- **WHEN** 保存点击打开新的标准确认框
- **AND** 确认框的确认按钮已可交互
- **THEN** 系统 MUST 以 `confirmation_required` 交接给后续 DSL 确认或取消步骤
- **AND** 系统 MUST 保留 `completion_signal`、`wait_duration_ms` 和 `fallback_used: false`
- **AND** 系统 MUST NOT 自动确认或伪造保存成功通知

#### Scenario: 确认框消失后保存仍在进行
- **WHEN** 后续确认点击关闭普通确认框并触发异步保存
- **AND** 尚未获得保存终态通知或有效动态模板证据
- **THEN** 系统 MUST NOT 仅凭该确认框消失结束保存相关等待

#### Scenario: 旧框不可操作或多个新框
- **WHEN** 仅有点击前已存在的确认框、禁用或被遮挡的确认按钮、无关子 frame 的确认框，或同时出现多个候选确认框
- **THEN** 系统 MUST NOT 以 `confirmation_required` 提前结束等待
- **AND** 缺少其他完成证据时 MUST 保持兼容超时

#### Scenario: 错误通知优先
- **WHEN** 点击同时产生错误通知和确认框变化
- **THEN** 系统 MUST 继续优先使用错误通知结束等待并保持既有负向断言规则
