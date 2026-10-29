## ADDED Requirements

### Requirement: 新参照可选数据就绪结束打开等待
工具栏或动作点击后，系统 SHALL 将新出现、标题与本次动作一致且确认入口可达的唯一前景参照及其可见子 frame 作为受限工作面。该工作面无局部加载且已出现可交互业务候选时 MUST 以 `popup_reference_ready` 结束通用等待。

#### Scenario: 父层确认按钮与子 frame 候选
- **WHEN** 点击前不存在目标参照，点击后出现标题匹配的前景层，其确认按钮可达且可见同源 iframe 内已呈现可选业务行
- **AND** 工作面及可见子 frame 均无加载状态
- **THEN** 系统 MUST 结束打开等待并允许后续参照选择，无需等到兼容超时
- **AND** 报告 MUST 包含 `completion_signal=popup_reference_ready` 和 `fallback_used=false`

#### Scenario: 参照尚未就绪
- **WHEN** 新参照仅有 iframe 外壳、空白内容、占位行、禁用候选，或者仍显示局部加载
- **THEN** 系统 MUST NOT 以参照就绪完成动作

#### Scenario: 无关或已存在工作面
- **WHEN** 只有点击前已存在的参照、标题不匹配的弹窗、背景候选、隐藏 iframe 或多个同名新工作面
- **THEN** 系统 MUST NOT 将这些证据作为本次参照就绪信号
