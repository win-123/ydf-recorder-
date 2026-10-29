## ADDED Requirements

### Requirement: 表单绑定排除串错 label_text 候选
系统 SHALL 在 `form.fill` 绑定表单字段时识别运行时标签串扰；当候选 runtime 元素只通过 `label_text` 匹配 DSL 字段名，但其自身可见文本、`name` 或等价字段身份明确指向另一个字段时，绑定结果 MUST NOT 选择该候选。

#### Scenario: 收款人全称不绑定到开户银行
- **WHEN** 模板字段 `收款人全称` 需要绑定可编辑表单控件
- **AND** runtime 中存在一个可见可编辑候选，其自身文本为 `开户银行`，但 `label_text` 被错误采集为 `收款人全称`
- **THEN** 绑定逻辑 MUST NOT 将该 `开户银行` 候选作为 `收款人全称` 的录入目标
- **AND** `form.fill` MUST 继续选择其它身份更一致的 `收款人全称` 候选，或在没有可靠候选时失败并报告未绑定字段

#### Scenario: 前景优先不得覆盖字段身份冲突
- **WHEN** 前景弹窗或抽屉中存在只靠 `label_text` 命中的候选
- **AND** 该候选自身文本或字段名与 DSL 字段名归一化后不一致
- **AND** 背景或同层存在自身文本、`fieldid`、模板 key、`dataField`、`aria_label` 或 `placeholder` 更明确匹配 DSL 字段名的候选
- **THEN** 绑定逻辑 MUST 优先选择字段身份一致的候选
- **AND** 绑定逻辑 MUST NOT 仅因为错误候选位于前景层就覆盖字段身份一致的候选
