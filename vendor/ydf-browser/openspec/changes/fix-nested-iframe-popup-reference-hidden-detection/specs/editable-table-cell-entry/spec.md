## MODIFIED Requirements

### Requirement: 可编辑表格 iframe 参照不得以临时内部值提前结束
系统 MUST 在 `editable_table.fill_row` 处理 iframe 式弹出参照时，将目标单元格真实回填和候选参照层真实关闭作为 `target-backfill` 提前结束的共同条件；候选点击后产生的参照字段根内部值不得单独证明字段录入完成，目标单元格仍显示“请选择”等空态占位文本时也不得视为已回填。

#### Scenario: 收款人候选已勾选但 iframe 参照仍可见
- **WHEN** DSL 文档为 `收款人信息.收款人全称` 执行 `first_available: true`
- **AND** 运行时已将第一条收款人候选勾选为 checked 或 selected
- **AND** 参照字段根已出现临时内部值，但目标单元格仍显示“请选择”或等价空值
- **AND** 当前页面或子 frame 中仍存在该字段的候选表格以及 `确定/确认/保存` 和 `取消` 动作
- **THEN** 运行时 MUST 将该 iframe 弹出参照判定为仍未关闭
- **AND** 运行时 MUST NOT 记录 `close_action=target-backfill` 后提前返回
- **AND** 运行时 MUST 点击当前前景参照内的确认动作并等待目标单元格真实回填

#### Scenario: first_available 空态占位文本不得作为回填证据
- **WHEN** DSL 文档为可编辑表格弹出参照列执行 `first_available: true`
- **AND** 候选已勾选但目标单元格仍显示“请选择”或等价空态占位文本
- **AND** 参照字段根读取结果与初始占位文本相同
- **THEN** 运行时 MUST 将该根读取结果视为未回填
- **AND** 运行时 MUST NOT 仅因根文本非空且目标是 plain first_available 就记录 `close_action=target-backfill`
- **AND** 运行时 MUST 继续等待候选层关闭和目标单元格真实回填

#### Scenario: 原参照 locator 失效但当前 frame 候选面仍存在
- **WHEN** 候选选择或 frame 重渲染导致最初解析的参照 locator 不可读或失效
- **AND** 当前页面或子 frame 中仍能识别同一业务参照的候选面、确认动作和取消动作
- **THEN** 运行时 MUST 以当前搜索上下文中的可见参照面判定参照仍未关闭
- **AND** 运行时 MUST NOT 仅因旧 locator 不可读而跳过确认动作

#### Scenario: 自动关闭且目标单元格已回填保持成功
- **WHEN** 可编辑表格参照候选点击后候选层真实关闭
- **AND** 目标单元格已经从占位或空值变为可识别业务值
- **THEN** 运行时 SHALL 保持既有 `target-backfill` 成功路径
- **AND** 运行时 MUST NOT 为本修复重复点击背景页面或已关闭参照中的确认动作
