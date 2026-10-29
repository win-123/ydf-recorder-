## Why

运行时 DOM 扫描会把视口外但可滚动到达的表单控件误判为确定不可接收 pointer，导致下方 `YDFTextArea` 等字段反复出现“平台精确身份状态不兼容”。同时，`editable_table.add_row` 已解析出唯一表格作用域后仍重新按全页身份寻找验证根，可能把背景列表行变化当成目标明细表证据。

## What Changes

- 将视口外控件的 pointer 可达性记录为未知，保留精确身份绑定，并由实际录入动作滚动到目标后完成交互。
- 保持视口内被遮挡、禁用或明确不接收 pointer 的控件继续失败关闭，避免恢复旧的背景字段误填风险。
- 将已解析 `ResolvedTableScope.token` 传入 `editable_table.add_row`，新增前后行状态优先在该唯一目标根内采集。
- 增加真实浏览器回归测试和需求调查登记真实 DSL 证据。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `form-field-entry`: 明确区分视口外未知 pointer 状态与视口内确定不可达状态，并规定未知状态的安全绑定边界。
- `editable-table-cell-entry`: 明确 `editable_table.add_row` 必须优先复用执行前已解析的表格作用域令牌验证行增长。

## Impact

- 运行时代码：`ydf_browser/runtime.py` 的 DOM 扫描与可编辑表格新增行验证。
- 测试：`tests/test_runtime.py` 的真实 Chromium DOM 回归。
- 不新增 DSL 字段，不改变 `editable_table.add_row` 的“显式新增一行”语义，不引入新依赖。
