## 1. 规则文档

- [x] 1.1 新增项目文档 `docs/ydf-fieldid-rules.md`，整理 YonDiF `divCode -> fieldid` 规则摘要，并引用 wiki 地址 `https://zw-wiki.yyrd.com/pages/viewpage.action?pageId=129282708`。
- [x] 1.2 在文档中列出已实现规则族：查询区、普通表单项、弹出参照、树、表格、按钮，并说明仍依赖运行时可见性和兜底的场景。

## 2. 规则推导核心

- [x] 2.1 增加轻量规则 helper，根据模板节点 `divCode`、`dataField`、组件类型和父 region 身份生成 expected runtime `fieldid` 候选。
- [x] 2.2 扩展 manifest candidate 诊断信息，保留规则候选来源，不改变现有 DSL schema。
- [x] 2.3 增加单元测试覆盖表单项、查询区、参照、树、表格和按钮的规则候选生成。

## 3. 定位链路接入

- [x] 3.1 将规则候选接入 binder，使 `fieldid` 推导候选优先于文本、placeholder、label_text 等弱匹配。
- [x] 3.2 将规则候选接入查询区和查询弹出参照定位，覆盖 `LCDQueryString` 查询按钮、模糊查询和参照子控件。
- [x] 3.3 将规则候选接入普通表单和弹出参照 `form.fill`，覆盖 `_input/_btn/_table/_tree/_modal_ok/_modal_cancel` 后缀。
- [x] 3.4 将规则候选接入树搜索、树节点标题、展开图标和 checkbox/radio 选择控件定位。
- [x] 3.5 将规则候选接入表格根、表头、表体、列和可编辑单元格定位，并保留现有 `data-field/data-index` 身份兜底。
- [x] 3.6 将规则候选接入工具栏按钮和下拉按钮父按钮定位，子项仍限定在可见 dropdown/popover 内选择。

## 4. 验证

- [x] 4.1 增加或更新 `tests/test_template_parser.py`、`tests/test_binder.py`、`tests/test_runtime.py`、`tests/test_executor.py` 中的最小回归测试，覆盖规则候选优先和失败回退。
- [x] 4.2 使用至少一个真实 YonDiF 用例验证规则候选没有破坏前景弹窗、查询、树、表格或工具栏动作中的既有成功链路。
- [x] 4.3 运行 `openspec validate support-fieldid-rule-based-location --strict`。
- [x] 4.4 运行 `./scripts/check_openspec_language.py --change support-fieldid-rule-based-location`。
- [x] 4.5 运行完整 `./.venv/bin/python -m pytest` 并确认全部通过。
