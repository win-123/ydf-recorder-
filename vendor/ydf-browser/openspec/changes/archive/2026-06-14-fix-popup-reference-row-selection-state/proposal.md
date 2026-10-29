## Why

`项目预算管理-业务` 的 `选择项目预算` 弹窗是一个主子表弹出参照。真实页面在点击主表第 1 行 radio 后，主表行会变成 `selected`，下方 `预算编制科目` 子表也会加载数据；但当前 runtime 仍要求行内 `input.checked` 或控件 class 呈现 checked 状态，导致 `popup_reference.select target.selections[].row_number` 误判失败。

已通过 1920x1080 headed 大窗口验证：页面本身可以选中，不是显示不全问题；失败发生在 runtime 对 WUI 表格参照行选中态的识别过窄。

## What Changes

- 扩展弹出参照表格行选择后的成功判定：当行点击后目标行或其等效行根呈现 `selected` / `active` / `current` / `aria-selected=true` 时，应视为已选中。
- 保持 row-number、match、first_available、selections 等既有 DSL 写法不变，不引入新的 DSL 字段。
- 修正 `选择项目预算` 这类主子表弹窗中“主表已选中但 input.checked 仍为 false”的误判。
- 补充回归测试，覆盖 WUI radio 行点击后只在行级 class 上体现 selected 的场景，以及主表选择后子表加载的真实用例验证。

## Capabilities

### New Capabilities

- `popup-reference-row-selection-state`: 描述弹出参照表格行选择后，runtime 如何判定候选行已被真实选中。

### Modified Capabilities

- 无。

## Impact

- 主要影响 `ydf_browser/runtime.py` 中弹出参照表格行点击、候选稳定和选中态判断逻辑。
- 影响 `tests/test_runtime.py` 中 popup reference row-number / first_available 相关回归。
- 需要用 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-项目预算-YDF-81116-0001.yaml` 或等价最小 probe 做真实验证。
- 不改变登录、菜单打开、`notification.close`、普通表格行选择、页面左树选择、普通下拉或弹窗确认按钮语义。
