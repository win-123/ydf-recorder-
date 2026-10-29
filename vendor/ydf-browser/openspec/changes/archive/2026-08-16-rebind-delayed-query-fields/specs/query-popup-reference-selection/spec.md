## ADDED Requirements

### Requirement: 查询动作重新绑定延迟出现的 manifest 字段
当当前页面 manifest 明确声明目标查询字段，但该字段在最近一次 binding 中尚未命中时，系统 SHALL 在报告字段未绑定前限时刷新当前 manifest 的运行时 binding；刷新命中后 MUST 使用该查询字段继续执行查询。

#### Scenario: 查询输入在页签绑定快照后出现
- **WHEN** `tab.click` 已完成且当前 manifest 声明查询字段“专家姓名”
- **AND** 页签步骤结束时的 binding 尚未包含该字段
- **AND** 运行时随后渲染出该查询输入
- **THEN** 紧接的 `query.search` MUST 刷新当前 manifest binding 并绑定“专家姓名”
- **AND** 查询 MUST NOT 因页签步骤的一次旧 binding 快照而报告“未绑定查询字段”

#### Scenario: 不把编辑表单字段当作查询字段
- **WHEN** `query.search` 请求的字段不属于当前 manifest 的查询字段
- **AND** 当前 manifest 声明保存、提交或取消等稳定编辑动作
- **THEN** 系统 MUST 报告该查询字段未绑定
- **AND** 系统 MUST NOT 将运行时同名普通表单字段作为查询字段兜底
