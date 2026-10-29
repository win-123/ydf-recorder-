## ADDED Requirements

### Requirement: 树表弹出参照支持右表列精确匹配
系统 MUST 在 `editable_table.fill_row` 的结构化弹出参照目标中支持 `tree + match` 组合：先应用弹窗内树上下文，再在同一活动参照弹窗的右侧候选表格中按 `match.column` 和目标值精确选择候选行。

#### Scenario: 物资分类按物资编码精确选择
- **WHEN** DSL 文档执行 `editable_table.fill_row`，目标表格为 `物资入库`
- **AND** 字段 `物资分类` 的模板列组件为 `YDFInput`
- **AND** 字段值包含 `tree.label: A05040101 复印纸`
- **AND** 字段值包含 `match.column: 物资编码` 和 `match.equals: A050401010000000001`
- **THEN** 运行时 MUST 将该字段值视为结构化弹出参照目标
- **AND** 运行时 MUST 打开或复用当前可见的物资类别参照弹窗
- **AND** 运行时 MUST 在该弹窗内选择 `A05040101 复印纸` 树上下文
- **AND** 运行时 MUST 在右侧候选表格中找到 `物资编码` 列值为 `A050401010000000001` 的候选行并选中
- **AND** 运行时 MUST 确认参照或等待目标单元格回填
- **AND** 运行时 MUST NOT 因候选表格使用 W table 渲染形态而报告 `headerCount=0` 或 `strictRowCount=0`

#### Scenario: 树上下文刷新后重新解析右表候选
- **WHEN** 结构化弹出参照目标先应用 `tree` 上下文
- **AND** 左树选择导致右侧候选表格异步刷新或重新渲染
- **THEN** 运行时 MUST 在执行 `match` 前重新解析当前活动参照弹窗内的候选根
- **AND** 运行时 MUST 等待右侧候选表格达到可匹配状态
- **AND** 运行时 MUST NOT 只在左树区域或刷新前的旧候选根内执行 `match`

### Requirement: 树表弹出参照精确匹配诊断
系统 SHALL 在树表弹出参照 `match` 选择失败时输出可判断根因的候选表格诊断，避免把运行时 DOM 识别失败误判为业务数据不存在。

#### Scenario: 目标行可见但未被识别时输出右表诊断
- **WHEN** 运行时已应用弹窗内 `tree` 上下文
- **AND** 字段值包含 `match.column` 和目标值
- **AND** 运行时未能选中目标候选行
- **THEN** 错误信息 MUST 包含目标列名、目标值、可见候选表头摘要、候选行摘要和截图路径
- **AND** 如果候选表格根未被识别，错误诊断 MUST 能体现候选表头数或候选行数为空
- **AND** 运行时 MUST 在当前字段失败，MUST NOT 继续录入后续列并把失败延迟到其他字段
