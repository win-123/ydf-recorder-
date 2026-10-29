## Why

`一上支出预算编制` 新增页的 `项目负责人` 是 `YDFReferSelect` 弹出参照，真实结构为左侧树、右侧查询区和表格单选，底部使用 `保存/取消`。当前运行时会打开弹窗但无法识别该弹窗根，因为弹窗识别和确认逻辑主要假定 `确定/确认` 按钮；结构化 `match` 也缺少左树上下文表达，导致用例无法稳定选择指定人员。

这类参照不同于已有的普通下拉、树下拉、表格参照和单列表参照，需要在 DSL 中表达“先选参照内左树，再在右表匹配行并保存”的业务语义。

## What Changes

- 扩展表单字段中的弹出参照目标语义，支持在 `form.fill` 字段值里声明参照内左树选择和右侧表格匹配。
- 支持 `YDFReferSelect` / `dataType=refer` 这类控件走弹出参照路径，而不是被普通 `YDFSelect`/choice 路径误处理。
- 扩展弹出参照识别和确认逻辑，识别底部为 `保存/取消` 的参照弹窗，并将 `保存` 作为默认确认动作之一。
- 保持已有普通下拉、树下拉、`YDFTableModalSelect`、`YDFTreeModalSelect` 和 `popup_reference.select` 用法兼容。
- 补充 DSL 文档、示例和回归测试，覆盖 `项目负责人` 树表参照的结构化写法。

## Capabilities

### New Capabilities

- `popup-reference-tree-table-selection`: 描述弹出参照中左树上下文、右侧表格行匹配、保存确认和回填校验的 DSL 与运行时行为。

### Modified Capabilities

- 无。

## Impact

- 影响 DSL 校验、运行时参照分流、弹窗根识别、弹窗确认按钮选择、参照内树节点选择、参照表格行定位和回填校验。
- 主要涉及 `ydf_browser/dsl.py`、`ydf_browser/runtime.py`、`ydf_browser/adapters.py`、`skills/gov-ydfdev-browser/references/dsl-reference.md`、示例 YAML 和相关测试。
- 不引入新外部依赖，不改变登录、菜单打开、页面左树选择、普通表单字段、普通 choice 下拉或已有表格行定位语义。
