## ADDED Requirements

### Requirement: 规则推导 fieldid 候选
系统 SHALL 基于 YonDiF 单据模板中的 `divCode`、`dataField`、组件类型和父容器身份，为可定位组件生成运行时 `fieldid` 候选，并在绑定和点击前优先使用这些候选。

#### Scenario: 根据父容器 divCode 和 dataField 生成表单字段候选
- **WHEN** 模板中存在父表单容器 `divCode=detailForm`，其子表单项 `dataField=userName` 且组件为 `YDFInput`
- **THEN** 系统 MUST 生成运行时身份候选 `detailForm_userName`
- **AND** binder MUST 在文本、placeholder 或宽泛 label 匹配前优先尝试该身份候选

#### Scenario: 规则候选不得绕过运行时校验
- **WHEN** 规则推导出的 `fieldid` 在 DOM 中存在多个候选或存在隐藏副本
- **THEN** runtime MUST 继续执行可见性、前景层、可编辑性、动作文本和 pointer event 可达性校验
- **AND** runtime MUST NOT 仅因规则候选命中就返回成功

### Requirement: fieldid 规则文档
项目 SHALL 提供一份专门文档，记录 ydf-browser 已采用的 YonDiF `divCode -> fieldid` 规则、规则来源和当前覆盖范围。

#### Scenario: 文档引用来源 wiki
- **WHEN** 本 change 实现完成
- **THEN** 项目文档 MUST 包含 wiki 来源地址 `https://zw-wiki.yyrd.com/pages/viewpage.action?pageId=129282708`
- **AND** 文档 MUST 说明该 wiki 可能需要用户 cookies，项目内规则摘要是后续实现和维护的直接参考

#### Scenario: 文档列出已实现规则族
- **WHEN** 开发者阅读项目文档
- **THEN** 文档 MUST 至少覆盖查询区、普通表单项、弹出参照、树、表格和按钮的已实现规则族
- **AND** 文档 MUST 标明仍依赖运行时验证或兜底的场景
