## ADDED Requirements

### Requirement: open_menu 合并同一逻辑工作面的嵌套重复根
系统 SHALL 在发现首次展示工作面时，将同一逻辑 identity 且存在 DOM 祖先包含关系的运行时可见根视为一个工作面，并 MUST 保留能够覆盖该组件加载状态、业务结果和明确空状态的最外层组件根。不相互包含的同 identity 可见根 MUST 继续作为独立工作面参与初始终态判定。

#### Scenario: 嵌套表格根只有外层包含明确空结果
- **WHEN** 同一主表的外层组件根与内层表格根重复使用同一 identity，外层包含内层，并且外层已显示明确空结果
- **THEN** 系统 SHALL 只将外层组件根计为一个首次展示工作面
- **AND** 内层根缺少独立空状态 MUST NOT 阻塞 `open_menu`

#### Scenario: 嵌套表格根仍在加载
- **WHEN** 同一主表存在重复嵌套根，并且最外层组件根或其内部后代仍处于加载状态
- **THEN** 该逻辑工作面 MUST 保持未完成
- **AND** `open_menu` MUST 继续等待业务行或明确空结果出现

#### Scenario: 同 identity 的并列可见实例
- **WHEN** 两个运行时可见根使用同一 identity 但不存在 DOM 祖先包含关系
- **THEN** 系统 MUST 将它们保留为两个独立首次展示工作面
- **AND** 任一实例尚未进入初始终态时 `open_menu` MUST 继续等待
