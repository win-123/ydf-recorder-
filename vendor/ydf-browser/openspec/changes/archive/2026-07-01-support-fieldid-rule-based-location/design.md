## Context

当前 ydf-browser 已经把 `fieldid` 当作最高置信度绑定身份：模板解析会把节点 `divCode/key` 写入 candidate，binder 会优先匹配 runtime `fieldid`，runtime 扫描也会采集 `[fieldid]`、`[data-fieldid]`、`uikey`。但很多真实 YonDiF 组件的最终渲染 `fieldid` 不是简单等于当前节点 `divCode`，而是由父容器、`dataField`、组件类型和固定后缀组合生成。

用户提供的 YonDiF wiki 说明了这些规则，地址为 `https://zw-wiki.yyrd.com/pages/viewpage.action?pageId=129282708`。该地址需要用户 cookies，不能作为实现阶段唯一事实源；本 change 要求把关键规则整理进项目文档。

## Goals / Non-Goals

**Goals:**

- 在模板解析后得到一组可诊断的 expected runtime `fieldid` 候选。
- 让表单、查询区、树、表格、参照和按钮优先使用规则推导出的身份定位。
- 保留现有前景弹窗、可见性、可点击性、表格作用域、横向滚动、hover 行按钮和文本兜底。
- 在项目文档中沉淀规则摘要，并引用 wiki 原始地址。

**Non-Goals:**

- 不新增 DSL 字段或 selector 写法。
- 不把 wiki 中所有历史组件一次性实现为强规则；先覆盖当前自动化高频组件。
- 不删除现有 class/text/geometry 兜底。
- 不把需要运行时数据的节点 key、行 key、下拉选项编号硬编码进模板解析。

## Decisions

1. 新增轻量规则 helper，而不是扩展散落 selector。

   从 `TemplateNode` / `ElementCandidate.raw` 读取 `divCode`、`dataField`、`name`、父 region `fieldid`，生成 `runtime_fieldids` 或等价候选集合。现有 candidate 的 `fieldid` 保持兼容，binder/runtime 先尝试规则候选，再回退当前字段。

2. 规则按组件族表达。

   - 容器：多数布局和面板使用自身 `divCode`。
   - 查询区 `LCDQueryString`：容器为 `divCode`，查询图标为 `<divCode>_query_icon`，模糊查询相关为 `<divCode>_fuzzy_*`，查询方案为 `<divCode>_plan/_btn`。
   - 表单项：普通输入、下拉、开关、复选、单选、日期、图片等主控件为 `<parentDivCode>_<dataField>`；子控件按 `_input/_suffix/_btn/_preview` 等后缀补充。
   - 弹出参照：输入框、按钮、弹表、弹树、确认、取消分别使用 `<parentDivCode>_<dataField>_input/_btn/_table/_tree/_modal_ok/_modal_cancel`。
   - 树：搜索框、搜索图标、展开图标、标题、checkbox 使用 `<treeDivCode>_search_input`、`_search_suffix`、`_tree_switcher_<key>`、`_tree_title_<key>`、`_tree_checkbox_<key>` 等候选。
   - 表格：表根为 `<divCode>_table`，表头/表体使用固定 `table-header/table-body`，列使用 `<tableFieldid>_<columnDataFieldOrName>`，可编辑单元格追加行序号。
   - 按钮：普通按钮和下拉按钮优先使用自身容器编码；下拉项仍需要运行时可见 dropdown 或数据属性确认。

3. 规则候选只提升置信度，不绕过运行时事实。

   即使 selector 命中，也必须继续校验可见、可编辑、非背景表格、前景弹窗优先、文本/动作身份匹配和 pointer event 可达。这样避免共享 `fieldid`、隐藏副本、固定底栏遮挡等已有问题复发。

4. 文档是交付物，不是测试替代。

   实现阶段新增 `docs/ydf-fieldid-rules.md`，记录规则来源、适用组件、已实现覆盖范围和不适用场景。每个规则族至少有一个单元测试；高风险链路需要真实页面用例验证。

## Risks / Trade-offs

- [Risk] wiki 规则和某些历史页面实际 DOM 不一致。→ Mitigation：规则候选失败后回退现有逻辑，并在诊断中标明候选和实际命中来源。
- [Risk] 错误生成的 `fieldid` 命中隐藏或错误副本。→ Mitigation：继续使用现有前景、可见性、可点击性和 label/action 身份过滤。
- [Risk] 一次覆盖太多组件导致回归面过大。→ Mitigation：先覆盖高频规则族，保留兜底，测试按链路聚焦。
- [Risk] wiki 需要 cookies，后续 agent 读不到。→ Mitigation：把规则摘要落项目文档，文档保留原始 wiki URL 作为来源引用。
