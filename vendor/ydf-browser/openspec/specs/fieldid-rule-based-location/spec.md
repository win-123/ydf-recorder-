# fieldid-rule-based-location Specification

## Purpose
定义由 YonDiF 模板身份推导运行时 fieldid 候选、绑定优先级、候选可信度和运行时校验边界，供 DSL 定位与动作执行共同使用。

## Requirements

### Requirement: 规则推导 fieldid 候选
系统 SHALL 将模板节点的 `key`、直接 `divCode`/fieldid、`dataField` 和父容器身份视为不同语义，并按 `platform-rendering-semantics` 中的稳定规则区分平台直接身份、平台后缀身份、模板命名约定和启发式。平台直接身份和已验证后缀身份 MUST 在绑定和点击前优先使用；模板命名约定和启发式只能进入 `unverified` 兼容路径。

#### Scenario: 表单字段优先使用节点直接身份
- **WHEN** 模板表单项声明 `divCode=userNameField`、`dataField=userName` 且组件为 `YDFInput`
- **THEN** 系统 MUST 将 `userNameField` 作为平台直接身份候选
- **AND** binder MUST 在文本、placeholder 或宽泛 label 匹配前按 `PRS-FORM-001` 校验该身份的当前运行时状态

#### Scenario: 父容器与 dataField 只是模板约定
- **WHEN** 模板父表单容器 `divCode=detailForm` 且子项只有 `dataField=userName`
- **AND** 平台直接身份不能证明子项 `fieldid=detailForm_userName`
- **THEN** 系统 SHALL 将 `detailForm_userName` 只作为模板命名约定候选
- **AND** 命中该候选的步骤 MUST 报告 `unverified`，MUST NOT 报告平台已验证身份

#### Scenario: 表格列使用平台证明的派生身份
- **WHEN** 表格 `divCode=table1` 且列 `dataField=code`
- **THEN** 系统 MUST 生成 `table1_code` 作为 `PRS-TABLE-001` 的平台后缀身份候选
- **AND** 系统 MUST NOT 将 `table1_table_code` 标记为平台已验证身份

#### Scenario: 精确身份命中但运行状态不合格
- **WHEN** 平台直接身份或已验证后缀身份唯一命中隐藏、disabled、readOnly、背景或不可接收 pointer 的组件
- **THEN** 当前操作 MUST 失败并保留身份与状态证据
- **AND** runtime MUST NOT 改选文本、placeholder 或标签相似的组件

#### Scenario: 精确身份不可用时有界降级
- **WHEN** 平台基线、组件变体或运行时 DOM 无法提供可用的直接身份或已验证后缀身份
- **THEN** 系统 SHALL 进入 `unverified` 有界兼容路径并报告稳定 `fallback_reason`
- **AND** 只有当前作用域内运行时证据唯一且安全时才能成功

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
