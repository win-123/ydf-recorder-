## MODIFIED Requirements

### Requirement: 弹出参照识别支持保存确认
系统 SHALL 识别页脚使用 `保存/取消` 而不是 `确定/确认` 的弹出参照弹窗，并且在参照前景层仍可见时不得跳过确认动作；即使参照弹窗的外壳 frame URL 或标题不包含参照关键字，运行时也不得据此误判参照已关闭。

#### Scenario: 识别保存取消结构的弹出参照
- **WHEN** 弹出参照字段打开前景弹窗，弹窗包含参照标题、候选树或表格内容，以及 `保存` 和 `取消` 页脚按钮
- **THEN** 运行时 MUST 将该弹窗解析为当前活动的弹出参照根
- **AND** 运行时 MUST NOT 仅因为弹窗缺少 `确定` 或 `确认` 就失败并提示“未打开弹出参照选择框”

#### Scenario: 使用保存按钮确认弹出参照
- **WHEN** 弹出参照候选行已被选择，且当前可见弹窗页脚包含 `保存`
- **THEN** 运行时 MUST 将 `保存` 作为默认弹出参照确认动作
- **AND** 运行时 MUST 在弹窗根内点击确认按钮，等待弹窗关闭或字段回填，并在结果中报告确认按钮标签

#### Scenario: iframe 参照仍可见时不得提前返回
- **WHEN** `form.fill` 已在 `PM_SELECT_MANAGER` 这类 iframe 式弹出参照中选中目标候选
- **AND** 当前页面或子 frame 中仍存在可见的参照候选树或表格，以及同一前景参照内的 `保存` 和 `取消` 页脚按钮
- **THEN** 运行时 MUST 判定该弹出参照仍未关闭
- **AND** 运行时 MUST NOT 以 `confirmed=false` 提前返回
- **AND** 运行时 MUST 点击该前景参照内的 `保存`，等待参照关闭或字段回填，并在步骤结果中报告 `confirmed=true` 和 `confirm_label=保存`

#### Scenario: 嵌套 iframe 外壳不因 URL 或标题关键字缺失误判关闭
- **WHEN** 弹出参照的 dialog 根只包含可见 iframe，实际候选表格、`确定/确认/保存` 和 `取消` 动作位于该 iframe 的子 frame 文档中
- **AND** 子 frame URL 与页面标题不包含 `select`、`reference`、`refer`、`参照`、`选择` 等参照关键字
- **THEN** 运行时 MUST 仍将该弹出参照判定为未关闭
- **AND** 运行时 MUST 将可见候选面搜索限定到 dialog 所包含的 frame，而不是仅依赖 URL 或标题关键字
- **AND** 运行时 MUST 点击当前前景参照内的确认动作，等待字段回填或弹窗关闭

#### Scenario: 显式确认按钮标签覆盖默认值
- **WHEN** 弹出参照目标声明 `confirm_label`
- **THEN** 运行时 MUST 在弹窗根内优先使用该标签作为确认动作
- **AND** 运行时 MUST 仍然要求命中的元素是可见的弹窗页脚动作
