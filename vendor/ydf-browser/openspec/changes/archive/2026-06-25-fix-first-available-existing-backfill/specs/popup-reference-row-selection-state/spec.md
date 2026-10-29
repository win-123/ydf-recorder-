## ADDED Requirements

### Requirement: first_available 参照字段已有值时保持幂等
系统 SHALL 在弹出参照 `first_available` 候选已成功选中后，允许表单字段已有非空可见值且确认后保持同值的场景判定为成功。

#### Scenario: first_available 选择已有同值字段
- **WHEN** `form.fill` 为表格型弹出参照字段提供 `first_available: true`
- **AND** runtime 已找到候选并确认候选呈现 checked、aria checked/selected、或明确 selected/checked 状态
- **AND** 字段选择前已有非空可见值
- **AND** 点击确认后字段可见值仍为同一个非空值
- **THEN** runtime MUST 判定该字段录入成功
- **AND** runtime MUST NOT 抛出 `弹出参照选择未回填到字段`

#### Scenario: first_available 无字段值仍失败
- **WHEN** `form.fill` 为弹出参照字段提供 `first_available: true`
- **AND** 候选选择或确认后目标字段仍读不到任何非空可见值
- **THEN** runtime MUST 继续按回填失败处理
- **AND** runtime MUST 保留诊断截图或候选诊断信息
