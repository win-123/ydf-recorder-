# YonDiF fieldid 生成规则摘要

来源 wiki：<https://zw-wiki.yyrd.com/pages/viewpage.action?pageId=129282708>

该 wiki 需要用户登录 cookies。本文档只记录 ydf-browser 已采用的定位规则摘要，后续实现和维护优先参考本文档；wiki 用于必要时核对原始说明。

## 总体规则

`divCode` 是模板容器编码，同一模板内唯一。很多运行时 `fieldid` 不是直接等于当前节点 `divCode`，而是由父容器、`dataField`、组件类型和固定后缀生成。

ydf-browser 使用这些规则生成 expected runtime `fieldid` 候选；候选命中后仍必须经过运行时可见性、前景弹窗、可编辑性、表格作用域和 pointer event 可达性校验。

## 已实现规则族

### 容器

- 大多数布局容器、面板、按钮容器使用自身 `divCode`。
- `LCDTable` 表格运行时根使用 `<divCode>_table`。
- `LCDTree` 树运行时根保留自身 `divCode`，并派生树内搜索控件候选。

### 查询区 `LCDQueryString`

- 查询区容器：`<divCode>`
- 执行查询图标：`<divCode>_query_icon`
- 模糊查询按钮：`<divCode>_fuzzy_btn`
- 模糊查询输入：`<divCode>_fuzzy_input`
- 执行模糊查询：`<divCode>_fuzzy_icon`
- 查询方案按钮：`<divCode>_btn`
- 查询方案列表：`<divCode>_plan`

### 普通表单项

普通表单项主控件使用：

```text
<父容器divCode>_<dataField>
```

适用组件包括 `YDFInput`、`YDFInputNumber`、`YDFSelect`、`YDFTreeSelect`、`YDFSwitch`、`YDFCheckbox`、`YDFRadio`、`YDFDatePicker`、`YDFDateRange`、`YDFTextArea`、`YDFHref`、`LCDImgUpload` 等。

常见子控件：

- 输入框：`<父容器divCode>_<dataField>_input`
- 下拉或日期图标：`<父容器divCode>_<dataField>_suffix`
- 图片预览：`<父容器divCode>_<dataField>_preview`
- 图片删除：`<父容器divCode>_<dataField>_preview_del`

`YDFSelect` 关闭时，内嵌搜索输入可能带 `readonly`，但下拉仍可点击选择。没有合格的直接控件、且同一身份根下唯一可见控件是未禁用的只读 combobox 搜索框时，外层、标签和内部容器只折叠到唯一且状态合格的 `uikey` 身份根；不会把标签当作输入框。静态只读展示区、多个身份根或多个可见控件仍不能通过该路径录入。可使用[财政账户状态查询真实回归](../tests/real_cases/fiscal_account_status_query_select.yaml)验证默认“启用”被精确替换为“草稿”。

### 弹出参照

适用组件包括 `YDFTableModalSelect`、`YDFTreeModalSelect`、`YDFReferSelect`。

- 输入框：`<父容器divCode>_<dataField>_input`
- `YDFTreeModalSelect` 内嵌搜索输入：`<父容器divCode>_<dataField>_input_search_input`
- 按钮图标：`<父容器divCode>_<dataField>_btn`
- 弹出表：`<父容器divCode>_<dataField>_table`
- 弹出树：`<父容器divCode>_<dataField>_tree`
- 确定按钮：`<父容器divCode>_<dataField>_modal_ok`
- 取消按钮：`<父容器divCode>_<dataField>_modal_cancel`
- 弹出树搜索输入：`<父容器divCode>_<dataField>_tree_search_input`
- 弹出树搜索图标：`<父容器divCode>_<dataField>_tree_search_search`

内嵌搜索输入只有在与外层精确身份属于同一逻辑根、且只有一个可见、可编辑且 pointer 状态不为明确不可达的真实输入时才能用于绑定；完全位于视口外的未知状态只按未验证契约绑定，同一逻辑根存在多个真实输入时必须继续报身份不兼容。

普通表单字段完全位于内部滚动容器的可见区域之外时，同样按未知 pointer 状态处理，即使字段矩形仍与浏览器窗口相交。唯一精确身份绑定后，`form.fill` 会滚动到目标并确认实际值，无需在 DSL 中增加滚动动作。部分可见字段只在有效可见区域判断命中；真实遮挡、禁用、只读、背景字段和多输入歧义仍不能作为录入目标。可使用[二上三级项目评审意见最小回归](../tests/real_cases/third_level_project_review_comment_scroll.yaml)验证小视口下的自动录入与字段值断言，用例不保存、不提交。

裁剪依据实际定位包含块计算：固定或绝对定位字段不会因无关 DOM 祖先的滚动口而被判为离屏；轴对齐缩放和 CSS `zoom` 的边界统一到视口坐标。内层 `hidden/clip` 完全裁掉输入且没有内部可恢复的 `auto/scroll` 滚动口时，即使外层可滚动也不能放行；内层滚动口确实能把输入移入外层可见范围时仍允许恢复。未知状态只允许进入录入检查，不代表可以强制写值：实际滚动后的点击若被拦截，文本录入会失败并保留原值。

### 树 `LCDTree`

- 搜索输入：`<treeDivCode>_search_input`
- 搜索图标：`<treeDivCode>_search_suffix`
- 节点展开图标：`<treeDivCode>_tree_switcher_<节点key>`
- 节点标题：`<treeDivCode>_tree_title_<节点key>`
- 节点内容：`<treeDivCode>_tree_content_<节点key>`
- 多选框：`<treeDivCode>_tree_checkbox_<节点key>`

节点 key 是运行时数据，模板解析阶段只生成树级候选；节点级候选必须在运行时已知 key 时使用。

### 表格 `LCDTable`

- 表格根：`<tableDivCode>_table`
- 表头：`table-header`
- 表体：`table-body`
- 表格行：`data-row-index="<序号>"` 或 `data-row-key="<id>"`
- 表格列：`<tableFieldid>_<dataField或列名>`
- 可编辑表格单元格：`<tableFieldid>_<dataField或列名>_<行序号>`
- 底部新增按钮：`<tableFieldid>_add_button`

表格仍必须保留现有 `data-field`、`data-index`、`data-key`、表头文本和表格作用域兜底。

### 按钮

- `YDFButton`、`YDFDropdownButton`、`YDFReferButton` 优先使用自身容器编码。
- 下拉按钮子项需要在已展开的可见 dropdown/popover 内匹配文本或数据属性，不能只靠全页面文本。

## 不适用或需运行时确认的场景

- 隐藏副本、固定底栏副本和共享 `fieldid` 必须继续做可见性和 pointer event 可达性判断。
- 前景弹窗或抽屉优先级不能被背景页同名字段覆盖。
- 表格树节点、普通树节点 key 和数据行 key 通常来自运行时数据，不应在模板解析阶段硬编码。
- 部分历史页面可能未完全遵循 wiki 规则；规则候选失败时必须保留现有兜底和诊断。
