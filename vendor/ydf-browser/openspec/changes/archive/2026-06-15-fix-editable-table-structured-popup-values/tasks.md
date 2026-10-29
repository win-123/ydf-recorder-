## 1. 回归复现与单测保护

- [x] 1.1 增加运行时单测，覆盖可编辑表格 `YDFInput` 列收到 `{tree, first_available}` 结构化目标时必须调用弹出参照流程，不能调用普通文本写入。
- [x] 1.2 增加失败路径单测，覆盖结构化参照目标无法打开弹窗时当前字段直接失败，错误中包含表格、行号、列名和结构化目标摘要。
- [x] 1.3 增加字段结果诊断单测，覆盖 `editable_table.fill_row` 成功录入结构化参照列时透传 `selected`、`popup_tree_context`、`confirmed`、`confirm_label`。
- [x] 1.4 增加兼容性单测，确认普通文本列、数字列和普通 choice/dropdown 列不因对象参照分流修改而改变既有行为。

## 2. 结构化参照分流实现

- [x] 2.1 在运行时增加结构化弹出参照目标识别 helper，统一识别 `tree`、`trees`、`tab`、`tabs`、`match`、`matches`、`row_number`、`row_numbers`、`first_available`、`select_first_available`、`selections`、`selection`、`values` 等目标键。
- [x] 2.2 调整 `_fill_active_editable_table_cell` 的分流顺序，让结构化参照目标早于普通文本、数字和 choice 写入，并且不受 `YDFInput` 模板元数据限制。
- [x] 2.3 对结构化参照目标执行 `_select_popup_reference`；如果参照流程失败，不允许回退到 `_set_text_field_value(str(value))` 或普通 choice 路径。
- [x] 2.4 支持激活单元格后已出现参照弹窗的场景，优先复用当前新增/前景参照根，再按既有触发器逻辑打开。
- [x] 2.5 保持既有 `YDFTreeModalSelect`、`YDFTableModalSelect`、`YDFReferSelect`、普通文本、数字和普通下拉录入行为兼容。

## 3. 诊断与错误收口

- [x] 3.1 结构化参照打开失败时，错误信息包含可编辑表格名、行号、列名、目标结构摘要、列身份和当前可见单元格/弹窗诊断。
- [x] 3.2 结构化参照选择后未回填时，在当前字段失败，错误明确指向“弹出参照选择未回填到目标单元格”。
- [x] 3.3 确保结构化参照字段成功后，`editable_table.fill_row` 字段级结果保留列身份、定位来源和参照诊断。
- [x] 3.4 确保失败发生在真实结构化参照字段，避免把被污染状态延迟到后续 `存放仓库` 或 `入库数量` 列才报错。

## 4. 文档、示例与真实验证

- [x] 4.1 更新 DSL 文档或相关示例，说明可编辑表格字段值可使用弹出参照结构化目标，且结构化目标不会被作为文本写入。
- [x] 4.2 准备或保留精简真实探针，覆盖 `物资分类: {tree: {label: A05040101 复印纸}, first_available: true}`。
- [x] 4.3 使用当前源码运行真实页面探针，验证 `物资分类` 不再写入 dict 字符串，并在报告字段结果中看到参照选择诊断。
- [x] 4.4 运行 `/Users/ken/temp/ydf-browser-问题反馈/实物管理-易耗品物资-入库填报-草稿页签删除-0002.yaml`，确认不再失败于 `物资分类` 字符串化导致的连锁问题；若后续暴露 `存放仓库` 标量参照独立问题，记录为独立发现。
- [x] 4.5 运行相关单测、`openspec validate fix-editable-table-structured-popup-values --strict`、DSL 校验和项目全量测试，确认回归通过。
