## ADDED Requirements

### Requirement: 可点击工具栏动作优先于遮挡诊断候选
系统 SHALL 在工具栏动作存在被遮挡的父页面身份候选和不同身份的前景精确同名候选时，使用与最终点击一致的可点击点探测规则筛选候选。可点击身份候选和精确同名候选 MUST 优先于被完全遮挡的身份诊断候选。

#### Scenario: 可点击身份按钮仍优先
- **WHEN** 模板身份对应的工具栏按钮可接收 pointer event，且标签或别名匹配
- **AND** 页面还存在不同身份的同名按钮
- **THEN** runtime MUST 保持身份按钮优先级

#### Scenario: 被遮挡父动作不抢占前景同名动作
- **WHEN** 工具栏动作的模板身份对应父页面同名按钮，且该按钮被前景工作面完全遮挡
- **AND** 当前主页面或子 frame 中存在不同身份、精确同名且可接收 pointer event 的工具栏按钮
- **THEN** runtime MUST 点击该可达按钮
- **AND** runtime MUST NOT 因保留父页面遮挡诊断候选而提前停止查找

#### Scenario: 全部候选不可达时保留遮挡诊断
- **WHEN** 工具栏身份候选被完全遮挡，且其它查找没有可点击目标
- **THEN** runtime MUST 保留身份候选的遮挡诊断并使动作失败
- **AND** runtime MUST NOT 使用强制点击报告成功
