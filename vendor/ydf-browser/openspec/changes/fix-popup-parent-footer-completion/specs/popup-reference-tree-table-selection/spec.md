## ADDED Requirements

### Requirement: iframe 候选与父级确认共同构成活动参照
系统 MUST 将当前参照弹窗内的可见 iframe 和外层确认动作共同识别为尚未关闭的参照，不要求确认按钮与候选表格位于同一文档。

#### Scenario: 父级确认按钮不被跳过
- **WHEN** 候选行已在弹窗内 iframe 中选中，且外层弹窗仍可见并包含确定按钮
- **THEN** 运行时 MUST 点击外层确认按钮并等待参照关闭
- **AND** MUST NOT 以 `closed_before_confirm=true` 提前返回成功

#### Scenario: 隐藏 iframe 不作为活动候选承载
- **WHEN** 参照根内只有隐藏 iframe，且不存在其他可见候选面
- **THEN** 运行时 MUST NOT 因该隐藏 iframe 判定参照仍处于活动状态
