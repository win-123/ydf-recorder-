## ADDED Requirements

### Requirement: 树控件使用规则推导身份
系统 SHALL 在普通页面树选择和搜索中使用 `LCDTree` 容器 `divCode` 推导树内搜索框、搜索按钮、节点标题、展开图标和选择控件的运行时 `fieldid` 候选。

#### Scenario: 树搜索框按 tree divCode 定位
- **WHEN** 模板中目标树 `divCode=deptTree`
- **THEN** runtime MUST 优先在目标树作用域内尝试 `deptTree_search_input` 作为搜索输入候选
- **AND** runtime MUST 优先尝试 `deptTree_search_suffix` 作为搜索触发候选

#### Scenario: 树节点 key 规则不扩大搜索范围
- **WHEN** runtime 已知目标节点 key 并能推导 `deptTree_tree_title_<key>` 或 `deptTree_tree_checkbox_<key>`
- **THEN** runtime MUST 只在已解析目标树根内使用这些候选
- **AND** runtime MUST NOT 因规则候选失败而点击树外同名文本
