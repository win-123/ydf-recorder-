## Why

`盘点任务下发` 新增页的 `存放地点` 字段是 `YDFTreeModalSelect` 弹出参照，过滤 `北京总仓` 后候选行左侧有 checkbox。当前 `first_available` 选择只让候选行视觉高亮，没有勾选 checkbox，确认时页面提示 `请选择数据！`，导致字段录入失败。

## What Changes

- 修正弹出参照 `first_available` 候选选择语义：候选项或候选行包含可见 checkbox/radio 时，必须确认选择控件真实选中后才算成功。
- 保持现有表格行、树节点、列表项和行级 selected 判定兼容；没有选择控件的候选仍按现有点击/回填语义处理。
- 为 `YDFTreeModalSelect` 这类轻量候选列表补充回归覆盖，避免视觉高亮被误判为业务选择。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `popup-reference-row-selection-state`: 补充 `first_available` 候选存在可见选择控件时必须勾选成功的要求。

## Impact

- 影响 `ydf_browser/runtime.py` 中弹出参照 `first_available` 候选识别、选择控件点击和选中态验证。
- 影响 `form.fill` 结构化参照字段和独立 `popup_reference.select` 复用的弹出参照选择路径。
- 不新增 DSL 字段，不改变 YAML 写法，不引入新依赖。
