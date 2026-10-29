## MODIFIED Requirements

### Requirement: 目标组件完成状态
- `rule_id: PRS-COMPLETE-004`
- `source_anchor: yondif-pvdf-fe/src/views/BillUIDesigner/components/LCDTable/LCDTable.jsx#reloadData`

查询和目标区域刷新 SHALL 使用本次动作绑定的精确目标组件状态。目标局部 busy 的 `0→1→0` 周期、关联响应后的目标后置条件或明确业务结果可以组成已验证信号；全页 busy、任意表格文本变化或 DOM 静默不得单独完成该动作。结果不变的查询 MUST 允许通过本次目标表格关联的成功响应、可观察业务行或明确空状态以及局部非忙状态完成。

#### Scenario: 目标表格局部 busy 周期完成
- **WHEN** 查询绑定到唯一目标表格
- **AND** 该目标表格在本次动作后经历局部 busy `0→1→0`
- **THEN** 系统 MUST 使用 `PRS-COMPLETE-004` 报告目标组件就绪
- **AND** 后续业务断言 MUST 继续验证所需目标值或空状态

#### Scenario: 背景表格变化不得完成查询
- **WHEN** 背景表格文本或全页 busy 在查询期间变化
- **AND** 精确目标表格没有本次动作相关的状态迁移或后置条件
- **THEN** 系统 MUST NOT 将该变化报告为已验证查询完成

#### Scenario: 同结果查询通过关联响应完成
- **WHEN** 本次查询的标准列表请求可通过唯一目标表格的实体、服务域和所在 frame 关联
- **AND** 请求在本次动作内发起、完整成功返回，目标表格可观察且局部非忙
- **THEN** 系统 MUST 使用 `target_component` 完成等待，即使表格文本与查询前一致

#### Scenario: 不完整或不相关响应不能结束等待
- **WHEN** 请求在动作前发起、身份不匹配、来自其他 frame、尚未完成或返回失败
- **THEN** 系统 MUST NOT 使用该响应完成查询
- **AND** 目标表格身份不唯一或缺少可观察终态时 MUST 保留既有有界兼容等待
