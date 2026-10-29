## ADDED Requirements

### Requirement: 弹出参照按钮绑定保持来源字段 owner
系统 SHALL 在 `form.fill` 绑定 `YDFTableModalSelect` 或 `YDFTreeModalSelect` 时，将同一平台精确身份根内唯一可见、未禁用且可接收 pointer 的参照按钮识别为该字段的直接控件，同时 MUST 保留唯一前景来源字段 owner 用于打开参照和确认回填。

#### Scenario: 唯一参照按钮消除包装节点歧义
- **WHEN** 同一平台精确身份根内存在多个 `div` 或 `label` 包装节点、不可编辑输入和一个唯一可接收 pointer 的参照按钮
- **AND** 模板字段组件为 `YDFTableModalSelect` 或 `YDFTreeModalSelect`
- **THEN** binder MUST 将该按钮识别为唯一直接控件
- **AND** `form.fill` MUST NOT 因包装节点重复而报告“平台精确身份状态不兼容”

#### Scenario: 多个参照按钮保持不兼容
- **WHEN** 同一平台精确身份根内存在两个或更多可见、未禁用且可接收 pointer 的参照按钮
- **THEN** binder MUST 保持平台精确身份状态不兼容
- **AND** binder MUST NOT 按 DOM 顺序选择其中一个按钮

#### Scenario: 唯一可编辑输入优先于参照按钮
- **WHEN** 同一平台精确身份根内同时存在一个唯一可编辑输入和一个或多个可接收 pointer 的参照按钮
- **THEN** binder MUST 将该输入识别为字段直接控件
- **AND** binder MUST NOT 因输入与按钮同时存在而报告平台精确身份状态不兼容

#### Scenario: 跨身份根控件保持不兼容
- **WHEN** 可编辑输入与参照按钮属于不同的平台精确身份根
- **THEN** binder MUST 保持平台精确身份状态不兼容
- **AND** binder MUST NOT 仅因存在唯一可编辑输入而忽略身份根冲突

#### Scenario: 多控件缺少身份根时保持不兼容
- **WHEN** 可编辑输入与参照按钮同时存在但均缺少可证明的身份根
- **THEN** binder MUST 保持平台精确身份状态不兼容
- **AND** binder MUST NOT 将缺失身份根视为两个控件属于同一身份根

#### Scenario: 参照选择从来源字段 owner 确认回填
- **WHEN** 唯一参照按钮已经绑定并打开候选工作面
- **AND** 用户目标已选择并确认
- **THEN** runtime MUST 从该按钮所属的唯一前景字段 owner 读取回填值
- **AND** runtime MUST NOT 因按钮自身没有字段值而误报“弹出参照选择未回填到字段”
