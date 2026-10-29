## Why

`popup_reference.select target.match.contains` 目前能通过 DSL 校验，但运行时表格候选匹配只读取 `equals/value/text`，导致合法用例在真实弹窗已有候选数据时仍失败。最近在 `/Users/ken/temp/ydf-browser-问题反馈/监督检查方案1.yaml` 中复现：弹窗过滤后只剩 `财会监督1`，但 `match.contains: 财会` 被运行时视为空目标值，报告 `wantedValue: ""`。

## What Changes

- 让弹出参照表格候选匹配正式支持 `match.contains`，并与 DSL 校验器已经接受的 `equals/contains` 语义保持一致。
- 让 `popup_reference.select`、结构化表单参照目标、`matches` / `selections` 中的表格行目标复用同一套 `contains` 处理。
- 让失败诊断中的 `wantedValue`、行调试和错误信息体现 `contains` 目标值，避免再次出现“目标值为空但页面有候选”的误导。
- 保持既有 `match.equals` 行为兼容，不改变 `filter.conditions[].equals` 的过滤写法。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `popup-reference-tree-table-selection`: 弹出参照目标结构中的表格行匹配需要支持 `match.contains`，运行时语义必须与 DSL 校验一致。

## Impact

- 影响 `ydf_browser/runtime.py` 中弹出参照表格候选行匹配、选择态稳定和诊断采集相关逻辑。
- 影响 `tests/test_runtime.py`、`tests/test_dsl.py` 中弹出参照 `match.contains` 的回归覆盖。
- 真实验证目标用例：`/Users/ken/temp/ydf-browser-问题反馈/监督检查方案1.yaml`。
- 不新增依赖，不改变登录、菜单打开、过滤条件填写、确认按钮识别或普通下拉选择行为。
