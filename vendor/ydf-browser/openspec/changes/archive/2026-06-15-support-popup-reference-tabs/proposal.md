## Why

`/Users/ken/temp/ydf-browser-问题反馈/ar01_报销管理_借款单填报 (1).yaml` 的最后一步在录入 `汇款转账.收款方户名` 时失败。真实参照已经打开到 `SETTMENTTAB` iframe，但默认停留在 `常用账户` 页签；目标数据 `苏康涯` 位于 `本单位人员账户` 页签，当前 DSL 无法表达“先切参照内页签，再搜索并按表格行选择”。

现有结构化参照目标已经支持 `tree`、`filter`、`match`、`row_number` 和 `first_available`，但缺少参照内部页签上下文，导致运行时只能在默认参照面内查找过滤字段或候选行。

## What Changes

- 扩展结构化弹出参照目标，新增 `tab` / `tabs` 上下文字段，用于表达弹出参照内部页签选择。
- 让 `form.fill`、`editable_table.fill_row`、`query.search` 和 standalone `popup_reference.select` 共享同一套参照页签目标语义。
- 运行时在打开并识别当前参照 shell / choice root 后，先在参照根内切换 `tab` / `tabs`，再执行已有 `tree`、`filter`、`match`、`row_number`、`first_available` 或 `selections` 选择流程。
- 支持无标签通用搜索框场景：用例可写 `filter: 苏康涯` 触发参照内右上角搜索框；`filter.conditions` 继续保留给有明确查询字段标签的参照。
- 步骤结果增加 `popup_tab_context` 诊断信息，并在可编辑表格单元格参照成功或失败时保留足够上下文。
- 补充 DSL 文档、示例和回归测试，覆盖 `收款方户名` 多页签参照。

## Capabilities

### New Capabilities

- `popup-reference-tab-context`: 描述弹出参照结构化目标中的内部页签上下文、执行顺序、作用域隔离和诊断报告。

### Modified Capabilities

- 无。

## Impact

- 影响 DSL 校验、结构化参照目标归一化、Playwright runtime 参照页签点击、可编辑表格参照诊断合并、DSL 文档、示例 YAML 和相关测试。
- 主要涉及 `ydf_browser/dsl.py`、`ydf_browser/runtime.py`、`ydf_browser/executor.py`、`skills/gov-ydfdev-browser/references/dsl-reference.md`、`examples/` 和 `tests/`。
- 不引入新外部依赖，不改变页面级 `tab.click` 语义，不改变现有 `tree`、`filter`、`match`、`row_number` 或 `first_available` 的既有行为。
