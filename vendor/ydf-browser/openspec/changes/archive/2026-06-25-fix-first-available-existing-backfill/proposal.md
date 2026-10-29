## Why

`form.fill` 对表格参照字段使用 `first_available: true` 时，真实页面可能已经存在同一个默认值。当前回填校验只接受“字段值发生变化”，导致候选已选中、弹窗已关闭、页面仍显示有效值时误报 `弹出参照选择未回填到字段`。

## What Changes

- 调整弹出参照 `first_available` 的回填确认：当字段确认后仍有可见非空值，且选择候选已通过选中态校验时，允许同值幂等成功。
- 保留普通参照选择的严格回填要求；没有有效字段值时仍必须失败并保留诊断截图。
- 增加针对已有值/同值 `first_available` 的回归测试和真实 YAML 验证。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `popup-reference-row-selection-state`: 补充 `first_available` 候选选中后，字段已有同值或回填同值时的成功判定要求。

## Impact

- 影响 `ydf_browser/runtime.py` 中弹出参照回填确认逻辑。
- 覆盖 `tests/test_runtime.py` 中 popup reference 的最小回归。
- 不引入新 DSL 字段、不改变用户 YAML 写法、不新增依赖。
