## ADDED Requirements

### Requirement: 前景业务弹窗内支持嵌套弹出参照字段
系统 SHALL 支持在前景业务弹窗、抽屉或 iframe 表单中通过 `form.fill` 填写 `YDFReferSelect` 等弹出参照字段，并将外层业务表单与内层候选参照选择框区分为不同上下文。

#### Scenario: 设置经费管理员弹窗内选择人员参照
- **WHEN** DSL 点击工具栏 `设置经费管理员` 后打开前景业务弹窗
- **AND** 前景业务弹窗内存在字段 `经费管理员`，字段模板组件为 `YDFReferSelect` 或等价弹出参照字段
- **AND** DSL 执行 `form.fill`，为 `经费管理员` 提供 `filter.conditions.field: 人员名称` 和 `match.column: 人员名称`
- **THEN** runtime MUST 在当前前景业务弹窗表单中定位 `经费管理员` 字段
- **AND** runtime MUST 点击该字段自身的参照触发控件打开内层人员候选参照
- **AND** runtime MUST 在内层候选参照中按 `人员名称` 查询和匹配候选行
- **AND** runtime MUST NOT 直接在外层业务弹窗中查找 `人员名称` 查询字段

#### Scenario: 外层业务表单不被当作候选参照根
- **WHEN** 当前可见前景层包含普通表单字段、附件区域以及 `确认/取消` 或 `保存/取消` 页脚动作
- **AND** 该前景层没有可选择的候选表格、候选树、候选列表或等价候选选择面
- **THEN** runtime MUST NOT 将该前景层解析为弹出参照候选根
- **AND** runtime MUST 继续等待或查找由目标字段触发后出现的内层候选参照根
- **AND** 如果内层候选参照未出现，错误诊断 MUST 保留外层前景层文本和 frame URL 或等价上下文信息

#### Scenario: 内层参照选择后恢复外层弹窗上下文
- **WHEN** runtime 已在内层候选参照中选中目标候选并确认
- **AND** 外层业务弹窗仍然可见
- **THEN** runtime MUST 将 `form.fill` 结果记录为对应字段已选择，并保留内层参照选择结果
- **AND** runtime MUST 保持外层业务弹窗作为当前前景表单上下文
- **AND** 后续 `toolbar.click`、`dialog.confirm` 或继续 `form.fill` MUST 作用于外层业务弹窗，而不是已关闭的内层参照根或背景列表页

#### Scenario: 页面级直接弹出参照保持兼容
- **WHEN** 页面表单字段直接打开候选树表参照，不经过外层业务弹窗
- **THEN** runtime SHALL 继续使用既有弹出参照树表选择语义
- **AND** 新增前景业务弹窗上下文识别 MUST NOT 要求 DSL 增加 selector、frame、层级或弹窗类型字段
