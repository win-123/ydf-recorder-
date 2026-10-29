## Why

YonDiF 单据模板到最终渲染页面存在稳定的 `divCode -> fieldid` 生成规则，但 ydf-browser 当前仍有不少定位路径依赖文本、class 或历史经验值兜底。把这些规则纳入定位链路，可以让表单、查询区、树、表格、参照和按钮优先使用模板身份定位，减少同名字段、重复按钮、隐藏副本和页面结构变化带来的猜测。

## What Changes

- 新增规则驱动定位能力：从 `matchingTemplate` 的 `divCode`、`dataField`、组件类型和父容器身份推导运行时 `fieldid` / `data-fieldid` 候选。
- 在现有 binder/runtime 之前优先尝试规则推导出的稳定身份；失败时保留当前可见性、前景弹窗、表格作用域、文本和 DOM 兜底逻辑。
- 覆盖第一批高收益组件：`LCDQueryString` 查询区、普通表单项、弹出参照、`LCDTree`、`LCDTable` / 可编辑表格列，以及工具栏按钮。
- 实现阶段必须把 YonDiF `fieldId` 生成规则整理为项目内专门文档，并在文档中引用当前 wiki 地址：`https://zw-wiki.yyrd.com/pages/viewpage.action?pageId=129282708`。
- 不引入新的 DSL 语法；这是定位稳定性增强和诊断增强。

## Capabilities

### New Capabilities

- `fieldid-rule-based-location`: 定义 ydf-browser 如何基于 YonDiF 官方 `divCode -> fieldid` 规则推导运行时定位身份，并将规则文档化。

### Modified Capabilities

- `form-field-entry`: 普通表单字段绑定需要优先使用规则推导出的字段身份。
- `tree-search-selection`: 树搜索、节点标题、展开图标和勾选控件定位需要可使用规则推导出的树内 `fieldid`。
- `table-column-assertions`: 表格根、表头、表体、列和可编辑单元格定位需要可使用规则推导出的表格身份。
- `toolbar-action-clicking`: 工具栏按钮和下拉按钮定位需要可使用规则推导出的按钮身份。
- `query-popup-reference-selection`: 查询区和参照弹层定位需要可使用规则推导出的输入框、按钮、弹表、弹树和确认/取消按钮身份。

## Impact

- 影响 `ydf_browser/template_parser.py`、`ydf_browser/binder.py`、`ydf_browser/runtime.py`、`ydf_browser/adapters.py` 及相关测试。
- 需要新增项目文档，建议路径为 `docs/ydf-fieldid-rules.md` 或同等稳定位置。
- 不需要新增依赖，不改变 DSL schema，不移除现有兜底 selector。
