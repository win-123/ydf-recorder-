## Why

`单位预算批复` 详情页中，`支出计划信息` 和 `项目预算信息` 两个页签各有一个同名 `隐藏0金额行` 字段，模板组件都是 `YDFCheckbox`。当前 `form.assert_values` 没有普通表单 checkbox 的状态读取语义，真实运行会把该字段读成邻近表格表头 `序号`，导致无法表达“详情页 checkbox 默认勾选”这类业务断言。

## What Changes

- 增加表单 `YDFCheckbox` 的状态读取能力，让 `form.assert_values` 可断言 checkbox 是否勾选。
- 为 checkbox 断言支持稳定语义值，例如 `on/off`、`true/false`、`1/0`、`是/否`、`勾选/未勾选`。
- 调整表单字段根定位和运行时读取，避免 checkbox 字段掉入通用文本兜底并读取到表格表头或邻近文本。
- 处理同名、同 `dataField`、同 `property_uri` 的跨页签 checkbox 字段，优先解析当前活动页签内真实可见且状态可读的字段。
- 在报告中继续保留 `fieldid`、`property_uri`、`actual` 等调试信息，便于确认命中的是 `hideZero` 还是 `hideZeroBgt`。
- 补充单测和真实用例验证，覆盖 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-预算批复-YDF-77108.yaml` 的两个页签断言。

## Capabilities

### New Capabilities

- `form-checkbox-state-values`: 定义表单 checkbox 字段在 `form.assert_values` 和相关读取流程中的状态语义、字段解析和报告行为。

### Modified Capabilities

- 无。

## Impact

- 影响 `ydf_browser/runtime.py` 中表单字段根定位、checkbox 状态读取、通用字段读值兜底和运行时元素采集。
- 影响 `ydf_browser/executor.py` 中 `form.assert_values` 字段候选选择，尤其是同名跨页签字段的解析。
- 影响 `ydf_browser/binder.py` 中运行时元素与模板字段的绑定评分或过滤逻辑。
- 需要补充 `tests/test_runtime.py`、`tests/test_executor.py`、必要时 `tests/test_binder.py` 的回归测试。
- 不引入新依赖，不改变登录、菜单打开、查询、表格行选择、switch、radio 或普通文本字段断言语义。
