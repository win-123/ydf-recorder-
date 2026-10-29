## ADDED Requirements

### Requirement: first_available 必须忽略空状态候选
系统 MUST 在弹出参照 `first_available` 候选发现中排除空状态、表头、分页、查询区、footer 和普通说明文本；这些节点不得作为右侧候选表格的数据行被点击或报告为已尝试业务候选。

#### Scenario: 空状态和真实业务行同时存在
- **WHEN** 弹出参照当前根内同时存在隐藏或非目标区域的 `暂无数据`、`暂时没有数据` 空状态文本，以及可见商品表格业务行
- **AND** DSL 使用 `first_available: true`
- **THEN** runtime MUST 忽略空状态候选
- **AND** runtime MUST 将可见商品业务行作为第一条可用候选尝试选择
- **AND** runtime MUST NOT 只尝试空状态候选后报告 `未找到弹出参照可选值`

#### Scenario: 只有空状态时保留失败诊断
- **WHEN** 弹出参照当前根内没有任何有效业务候选行、树节点或列表项
- **AND** 只存在 `暂无数据`、`暂时没有数据` 或等价空状态文本
- **THEN** runtime MUST 让 `first_available` 选择失败
- **AND** 失败诊断 SHALL 说明当前没有有效候选，并保留空状态摘要或截图

### Requirement: first_available 可见表格行必须按业务行选择
系统 MUST 将可见表格中的第一条有效业务数据行识别为 `first_available` 的右表候选，并在该行包含 radio 或 checkbox 时验证真实选中态。

#### Scenario: 商品参照只有一条可见业务行
- **WHEN** `YDFTableModalSelect` 商品参照弹窗显示一条业务行，例如 `0702154531736 / 商品_0702154531736`
- **AND** 该行左侧存在可见且未禁用的 radio
- **AND** DSL 使用 `first_available: true`
- **THEN** runtime MUST 点击该业务行的 radio 或等价可交互包装节点
- **AND** runtime MUST 验证该行、radio 或等价选择控件进入 checked、selected 或 aria checked/selected 状态
- **AND** runtime MUST NOT 将查询框、表头、分页、footer 或空状态文本作为最终候选

#### Scenario: 业务行可见但未能选中时失败
- **WHEN** `first_available` 已识别出可见业务表格行
- **AND** runtime 点击该行或其选择控件后仍无法读取有效选中态
- **THEN** runtime MUST 继续尝试同一有效候选集合中的下一个业务候选
- **AND** 如果没有候选能进入有效选中态，runtime MUST 失败并保留候选文本、候选来源、是否要求选择态和截图路径
