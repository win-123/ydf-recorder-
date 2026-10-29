## ADDED Requirements

### Requirement: 工具栏动作使用规则推导身份
系统 SHALL 在执行 `toolbar.click` 和动态下拉按钮点击时，优先使用按钮组件自身容器编码和下拉项数据属性定位动作候选。

#### Scenario: 普通按钮使用容器编码定位
- **WHEN** 模板中工具栏 `leafItem` 或按钮组件 `divCode=btnSave`，标签为 `保存`
- **THEN** executor MUST 将 `btnSave` 作为动作身份传递给 runtime
- **AND** runtime MUST 在文本兜底前优先尝试 `[fieldid="btnSave"]` 或等价 `data-fieldid` 候选

#### Scenario: 下拉按钮子项仍需可见菜单确认
- **WHEN** DSL 执行 `toolbar.click` 且目标包含 `label=新增`、`sub_label=租赁合同`
- **AND** 模板中父按钮为 `YDFDropdownButton`
- **THEN** runtime MUST 先按父按钮容器编码打开可见下拉菜单
- **AND** runtime MUST 在可见 dropdown/popover 范围内选择匹配 `sub_label` 或数据属性的子项
