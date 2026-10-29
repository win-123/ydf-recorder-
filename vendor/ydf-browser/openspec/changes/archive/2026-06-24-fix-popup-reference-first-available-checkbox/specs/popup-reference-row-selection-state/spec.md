## ADDED Requirements

### Requirement: first_available 候选选择控件必须真实选中
系统 SHALL 在弹出参照 `first_available` 选择中识别候选项、候选行或候选树节点内的可见选择控件，并且在选择控件真实选中后才报告候选选择成功。

#### Scenario: YDFTreeModalSelect 候选 checkbox 在确认前被勾选
- **WHEN** `form.fill` 为 `YDFTreeModalSelect` 字段提供 `filter` 和 `first_available: true`
- **AND** 过滤后的第一个可用候选显示为轻量列表或树节点，例如 `A01 北京总仓`
- **AND** 该候选文本前存在可见且未禁用的 checkbox
- **THEN** runtime MUST 点击该 checkbox 或其可交互包装节点
- **AND** runtime MUST 在确认弹窗前验证该候选已呈现 checked、aria checked/selected、或明确 selected/checked 状态
- **AND** runtime MUST NOT 仅因候选文本行视觉高亮就报告选择成功

#### Scenario: 未勾选的 first_available 候选不能被接受
- **WHEN** `first_available` 候选包含可见 checkbox 或 radio
- **AND** runtime 点击候选文本、候选行和选择控件后仍无法读取到有效选中态
- **THEN** runtime MUST 继续尝试同一候选集合中的下一个可选择候选
- **AND** 如果没有候选能进入有效选中态，runtime MUST 失败并保留 first available 候选诊断
- **AND** runtime MUST NOT 点击确认按钮后把页面提示 `请选择数据！` 误报为字段已录入

#### Scenario: 无选择控件的候选保持兼容
- **WHEN** `first_available` 候选范围内的第一个可用候选没有可见 checkbox 或 radio
- **THEN** runtime SHALL 保持既有候选点击、自动关闭或字段回填判定行为
- **AND** runtime MUST NOT 要求这类候选额外呈现 checked 状态
