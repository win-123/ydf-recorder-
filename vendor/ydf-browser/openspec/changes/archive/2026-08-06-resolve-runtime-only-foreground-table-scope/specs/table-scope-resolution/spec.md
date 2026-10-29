## ADDED Requirements

### Requirement: manifest 未声明的精确表格 fieldid 按运行时解析
系统 MUST 在 `target.table` 未匹配当前 manifest 的表格身份时，将该值作为精确 runtime fieldid 对当前 DOM 进行一次受限探测。只有该 fieldid 对应唯一、可见、可交互的前景表格且包含动作全部必需列时，系统 SHALL 解析成功；系统 MUST NOT 将该兜底扩展为表格名称猜测或改选其它表格。

#### Scenario: 动态模板弹窗中的运行时表格解析成功
- **WHEN** 动态模板弹窗已渲染出 manifest 未声明的表格
- **AND** `target.table` 精确等于该表格的 runtime fieldid
- **AND** 该表格是唯一、可见、可交互的前景根并包含动作全部必需列
- **THEN** 系统 MUST 将该运行时表格解析为当前步骤的表格作用域

#### Scenario: 运行时精确 fieldid 不满足约束时失败
- **WHEN** `target.table` 未匹配 manifest 且按精确 runtime fieldid 探测的表格不存在、不可见、不可交互、位于背景或缺少必需列
- **THEN** 步骤 MUST 在产生页面副作用前失败
- **AND** 系统 MUST NOT 回退到同名表格、其它含有所需列的表格或全页面文本匹配

#### Scenario: 非精确名称不触发运行时猜测
- **WHEN** `target.table` 仅提供未匹配 manifest 的业务名称
- **AND** 该名称不等于任一运行时表格 fieldid
- **THEN** 系统 MUST 保持现有 manifest 候选匹配和排除语义
- **AND** 系统 MUST NOT 根据标题、列名或相似文本猜测运行时表格身份
