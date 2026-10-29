## MODIFIED Requirements

### Requirement: 页面提示断言
系统 SHALL 支持 `notification.assert` 断言最近一次动作捕获到的页面提示。

#### Scenario: 断言最近一次动作捕获的错误提示
- **WHEN** 用例在 `toolbar.click`、`action.click`、`dialog.click`、`tab.click` 或 `table_row_action.click` 后执行 `notification.assert`，且 `target.type` 为 `error`、`target.contains` 命中最近一次动作捕获的错误提示文本
- **THEN** `notification.assert` 步骤 MUST 成功
- **AND** 步骤结果 MUST 包含命中的 `notification` 和参与匹配的 `notifications`

#### Scenario: 断言最近一次行级动作捕获的短成功提示
- **WHEN** 用例执行 `table_row_action.click` 且页面短暂出现 `操作成功`
- **AND** 该提示在后续动态模板等待期间已从 DOM 消失
- **AND** 下一步执行 `notification.assert` 且 `target.message` 为 `操作成功`
- **THEN** `notification.assert` 步骤 MUST 成功
- **AND** 步骤结果 MUST 包含行级动作捕获到的成功提示

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

#### Scenario: 行级动作未预期错误提示导致点击失败
- **WHEN** `table_row_action.click` 完成后捕获到 `type=error` 的页面提示
- **AND** 下一步不是 `notification.assert`
- **THEN** 当前行级动作步骤 MUST 标记失败
- **AND** 错误信息 MUST 包含真实错误提示文本

#### Scenario: 紧接断言允许预期错误继续
- **WHEN** 点击类动作完成后捕获到 `type=error` 的页面提示，且下一步是 `notification.assert`
- **THEN** 当前点击步骤 MUST 保持成功状态，使 `notification.assert` 能校验该预期负向提示
- **AND** 系统 MUST NOT 因该错误提示在断言前中断用例
