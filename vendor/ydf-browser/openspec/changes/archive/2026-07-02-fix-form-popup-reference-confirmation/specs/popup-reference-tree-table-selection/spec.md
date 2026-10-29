## ADDED Requirements

### Requirement: 普通表单弹出参照必须确认完成
系统 SHALL 在 `form.fill` 处理普通表单弹出参照字段时，将候选选择、确认动作、字段回填和候选层关闭作为同一个字段录入完成条件；仅记录 `selected` 但 `confirmed=false` 的结果 MUST NOT 被视为字段录入成功。

#### Scenario: 人员参照未确认不得通过
- **WHEN** `form.fill` 为 `项目联系人` 或 `项目负责人` 这类 `YDFReferSelect` 普通表单字段提供 `filter.conditions.field: 人员名称` 和 `match.column: 人员名称`
- **AND** runtime 已匹配或点击目标候选，并在步骤结果中记录 `selected`
- **AND** runtime 未能确认弹出参照关闭或字段真实回填，导致参照结果为 `confirmed=false`
- **THEN** 当前 `form.fill` 字段录入 MUST 失败
- **AND** 用例整体 MUST NOT 报告 `passed`
- **AND** 失败诊断 MUST 包含字段名、候选目标和未确认关闭或未回填的原因

#### Scenario: 人员参照确认关闭后通过
- **WHEN** `form.fill` 为 `项目联系人` 或 `项目负责人` 选择人员候选
- **AND** runtime 点击当前前景参照内的 `保存`、`确定`、`确认` 或等价确认动作
- **AND** runtime 证明候选参照层已关闭且字段值已回填为目标人员
- **THEN** 当前字段录入 MUST 成功
- **AND** 步骤结果 MUST 包含 `selected`、`confirmed=true`，并在可读时包含 `confirm_label`

#### Scenario: 自动关闭参照必须证明回填
- **WHEN** 普通表单弹出参照在点击候选后自动关闭
- **THEN** runtime MUST 在返回成功前确认目标字段可见值、隐藏值或等价字段状态已回填目标候选
- **AND** runtime MUST 确认当前页面和相关 frame 中不再存在该字段打开的候选参照层
- **AND** 如果任一确认失败，当前字段录入 MUST 失败

### Requirement: 弹出参照早退只允许有后续回填校验的路径
系统 MUST 将候选点击后跳过确认按钮的早退语义限制在有独立后续回填校验的路径中，例如可编辑表格单元格参照；普通表单 `form.fill` 字段不得复用该早退作为成功条件。

#### Scenario: 普通表单不复用可编辑表格早退
- **WHEN** 普通表单弹出参照候选点击后未读到候选选中态
- **AND** runtime 的快速状态判断认为候选面可能已关闭
- **THEN** runtime MUST 继续尝试当前参照的确认动作或执行普通表单字段回填校验
- **AND** runtime MUST NOT 仅以 `selected` 和 `confirmed=false` 返回成功

#### Scenario: 可编辑表格保留外层回填兜底
- **WHEN** `editable_table.fill_row` 的参照单元格候选点击后候选层关闭但候选选中态不可读
- **THEN** runtime SHALL 允许将控制权返回给可编辑表格单元格回填等待逻辑
- **AND** 该单元格回填等待 MUST 仍然负责最终判定成功或失败
- **AND** 普通表单字段成功条件 MUST NOT 因该兜底而放宽

### Requirement: 弹出参照未确认诊断可追踪
系统 SHALL 在 `form.fill` 弹出参照字段未确认完成时保留可追踪诊断，帮助区分候选未命中、确认按钮未点击、候选层仍可见、候选层误判隐藏和字段未回填。

#### Scenario: 报告保留未确认原因
- **WHEN** 普通表单弹出参照字段失败于未确认完成
- **THEN** 错误信息或步骤诊断 MUST 包含字段名和目标选择结构
- **AND** 诊断 SHOULD 包含 `close_action`、字段回填检测结果、候选层可见性判断或确认按钮标签中的至少一种

#### Scenario: 成功报告保留确认路径
- **WHEN** 普通表单弹出参照字段确认完成
- **THEN** 步骤结果 MUST 记录该字段的 `confirmed=true`
- **AND** 如果 runtime 点击了确认动作，步骤结果 MUST 在可读时记录 `confirm_label`
- **AND** 如果 runtime 通过自动关闭和回填证明成功，步骤结果 MUST 记录等价的关闭或回填证据
