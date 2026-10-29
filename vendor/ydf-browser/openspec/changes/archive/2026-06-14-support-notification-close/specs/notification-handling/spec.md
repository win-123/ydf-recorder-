## ADDED Requirements

### Requirement: 页面提示断言
系统 SHALL 支持 `notification.assert` 断言最近一次动作捕获到的页面提示。

#### Scenario: 断言最近一次动作捕获的错误提示
- **WHEN** 用例在 `toolbar.click`、`action.click`、`dialog.click` 或 `tab.click` 后执行 `notification.assert`，且 `target.type` 为 `error`、`target.contains` 命中最近一次动作捕获的错误提示文本
- **THEN** `notification.assert` 步骤 MUST 成功
- **AND** 步骤结果 MUST 包含命中的 `notification` 和参与匹配的 `notifications`

#### Scenario: 断言等待稍后出现的目标提示
- **WHEN** 最近一次动作只捕获到 `正在处理，请稍候...` 等中间提示，且 `notification.assert` 的目标提示稍后才出现
- **THEN** executor MUST 短轮询当前可见提示和缓冲提示
- **AND** 如果目标提示在等待窗口内出现，步骤 MUST 成功

#### Scenario: 断言不自动关闭提示
- **WHEN** `notification.assert` 命中一个仍可见的持久错误提示
- **THEN** 系统 MUST NOT 自动点击该提示的关闭图标、`关闭`、`确定` 或其他按钮
- **AND** 后续是否清理该提示 MUST 由显式 `notification.close` 步骤表达

### Requirement: 未处理错误提示保护
系统 MUST 将点击类动作后出现的未处理错误提示视为该动作失败，除非下一步紧接 `notification.assert` 显式声明该错误为预期结果。

#### Scenario: 未预期错误提示导致点击动作失败
- **WHEN** 点击类动作完成后捕获到 `type=error` 的页面提示，且下一步不是 `notification.assert`
- **THEN** 当前点击步骤 MUST 标记失败
- **AND** 错误信息 MUST 包含真实错误提示文本
- **AND** 错误信息 MUST 引导作者在该错误是预期结果时紧接 `notification.assert`

#### Scenario: 紧接断言允许预期错误继续
- **WHEN** 点击类动作完成后捕获到 `type=error` 的页面提示，且下一步是 `notification.assert`
- **THEN** 当前点击步骤 MUST 保持成功状态，使 `notification.assert` 能校验该预期负向提示
- **AND** 系统 MUST NOT 因该错误提示在断言前中断用例

### Requirement: 页面提示显式关闭
系统 SHALL 支持 `notification.close` 关闭当前可见、且匹配目标条件的页面提示。

#### Scenario: 关闭匹配的持久错误提示
- **WHEN** 当前页面存在可见错误提示，文本包含 `请联系管理员`
- **AND** 用例执行 `notification.close`，且 `target.type=error`、`target.contains=请联系管理员`
- **THEN** runtime MUST 定位匹配的提示根节点
- **THEN** runtime MUST 在该根节点内点击关闭入口
- **AND** 步骤 MUST 成功并报告已关闭提示文本

#### Scenario: 关闭匹配的 modal-confirm 错误提示
- **WHEN** 预期错误提示以 `modal-confirm` 形态显示，并且根节点文本匹配 `target.contains`
- **THEN** runtime MUST 将该 confirm 根作为提示根处理
- **AND** runtime MUST 在该根内点击 `target.label` / `target.button` 指定按钮，或默认候选 `关闭`、`确定`、`确认`、`我知道了`、`OK` 中的可见按钮
- **AND** runtime MUST NOT 点击该 confirm 根之外的同名按钮

#### Scenario: 关闭普通 notification 的 close icon
- **WHEN** 匹配提示为普通 notification/message 根，并存在 close icon、`aria-label=close`、`title=关闭` 或等效关闭控件
- **THEN** runtime MUST 优先点击该提示根内的关闭控件
- **AND** runtime MUST NOT 因页面其他位置存在 `关闭` 文本而点击全页面按钮

#### Scenario: 未找到匹配提示时失败
- **WHEN** 用例执行 `notification.close`，但当前可见提示中没有任何一条满足 `target.type` 和文本条件
- **THEN** 步骤 MUST 失败
- **AND** 错误信息 MUST 包含期望条件和当前实际可见提示摘要

#### Scenario: 匹配提示没有可点击关闭入口时失败
- **WHEN** runtime 已定位匹配提示根，但根内不存在可见可点击的关闭入口
- **THEN** 步骤 MUST 失败
- **AND** 错误信息 MUST 包含匹配提示文本和关闭候选诊断

#### Scenario: 关闭后校验提示不再可见
- **WHEN** runtime 点击匹配提示的关闭入口
- **THEN** runtime MUST 等待该匹配提示根消失，或等待同一 `type/message` 的提示不再可见
- **AND** 如果等待后同一提示仍可见，步骤 MUST 失败

### Requirement: 页面提示关闭后的执行器状态
系统 MUST 在 `notification.close` 成功后刷新最近提示缓存，避免已处理错误继续影响后续步骤。

#### Scenario: 关闭预期错误后继续点击业务按钮
- **WHEN** 用例执行点击动作后捕获错误提示，随后依次执行 `notification.assert` 和 `notification.close`
- **THEN** `notification.close` 成功后 executor MUST 用当前剩余可见提示刷新 `_last_notifications`
- **AND** 后续 `toolbar.click`、`action.click`、`dialog.click` 或 `tab.click` MUST NOT 因已关闭的旧错误提示被判定为未处理错误

#### Scenario: 保留其他仍可见提示
- **WHEN** `notification.close` 只关闭其中一条匹配提示，页面上仍存在其他可见提示
- **THEN** 步骤结果 MUST 报告 `remaining_notifications`
- **AND** executor 的最近提示缓存 MUST 反映这些仍可见提示

### Requirement: 页面提示 DSL 校验
系统 SHALL 在业务执行前校验 `notification.assert` 和 `notification.close` 的 target 结构。

#### Scenario: 接受关闭提示目标
- **WHEN** DSL 文档包含 `notification.close`，且 target 至少包含 `type`、`contains`、`message_contains`、`text_contains`、`message` 或 `equals` 中任一匹配字段
- **THEN** DSL validation MUST 接受该步骤

#### Scenario: 拒绝空关闭目标
- **WHEN** DSL 文档包含 `notification.close`，但 target 没有任何匹配字段
- **THEN** DSL validation MUST 失败
- **AND** 错误信息 MUST 说明 `notification.close` 缺少提示匹配条件

#### Scenario: 接受显式关闭按钮标签
- **WHEN** DSL 文档包含 `notification.close`，且 target 使用 `label` 或 `button` 指定关闭按钮
- **THEN** DSL validation MUST 接受该字段
- **AND** runtime MUST 仅在匹配提示根内使用该按钮标签
