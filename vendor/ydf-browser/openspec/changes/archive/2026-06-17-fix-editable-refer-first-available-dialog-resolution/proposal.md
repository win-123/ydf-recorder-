## Why

真实用例 `/Users/ken/temp/ydf-browser-问题反馈/功能-网上报销-报销管理-还款单填报-按钮-0011.yaml` 近期回归：前 6 步成功后，`editable_table.fill_row` 录入 `汇款转账.收款方户名` 的 `{filter: 严巴天, first_available: true}` 失败。报告显示运行时没有拿到真正的收款方参照候选层，却在还款单主页面的 `关联单据/借款信息` 区域查找候选，最终报 `结构化弹出参照目标录入失败`。

这次修复需要收窄可编辑表格结构化参照的弹层复用和候选根识别边界，避免把背景页面、外层业务表单或旧上下文当成当前候选参照；同时必须保留最近几天新增的结构化可编辑表格参照、树表 `first_available`、`match.contains`、iframe 保存确认和前景业务弹窗内嵌套参照能力。

## What Changes

- 修正 `editable_table.fill_row` 中 `YDFReferSelect` / `dataType=refer` 列处理 `{filter, first_available}` 时的弹出参照打开与解析逻辑：只有真实候选参照根可见时才进入候选选择。
- 明确 `reuse_existing_dialog` 的适用边界：只能复用当前字段触发的候选参照层或已经打开的候选参照层，不能把背景编辑页、业务助手、外层业务表单、普通内容卡片或旧的已关闭/已失效上下文当作候选参照。
- 当结构化目标无法打开或解析候选参照根时，错误应直接说明“未打开/未解析当前字段参照候选层”，并保留字段、表格、行号、可见页面和截图诊断；不能继续在主页面文本中查找 `first_available` 候选。
- 保持现有 DSL 不变，继续支持 `{filter, first_available}`、`tree + first_available`、`tree + match`、`match.contains`、`row_number`、`selections`、iframe `保存` 确认和前景弹窗内嵌套参照。
- 增加回归测试和真实用例验证，覆盖还款单 `汇款转账.收款方户名` 场景，并防止最近几天相关修复被回退。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `editable-table-cell-entry`: 可编辑表格结构化参照目标在没有真实候选参照根时必须失败在当前字段的弹层解析阶段，不能误用背景页面或回退到错误候选面。
- `popup-reference-tree-table-selection`: 弹出参照候选根识别和前景业务弹窗嵌套参照语义需要区分外层业务表单、背景页面和内层候选参照，并约束可复用弹层的有效性。

## Impact

- 主要影响 `ydf_browser/runtime.py` 中可编辑表格参照列分流、`_select_popup_reference()` 的弹层打开/复用、候选根识别、`first_available` 候选选择和失败诊断。
- 需要补充 `tests/test_runtime.py`、必要时补充 `tests/test_executor.py`，覆盖当前回归和最近相关能力的非回退场景。
- 不新增 DSL 语法，不改变现有 YAML 用例写法，不引入新依赖。
- 真实验证至少包括还款单用例 `/Users/ken/temp/ydf-browser-问题反馈/功能-网上报销-报销管理-还款单填报-按钮-0011.yaml`，并保留报告路径作为证据。
