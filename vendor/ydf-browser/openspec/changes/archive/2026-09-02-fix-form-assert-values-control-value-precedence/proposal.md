## Why

`form.assert_values` 在普通输入或弹出参照已有非空控件值时，仍可能把该值当作页面标签再次查找，导致相邻字段标签被误报为实际值。开户银行真实回填为“中信银行”，断言却读取成“账户性质”，使有效回归无法验证业务结果。

## What Changes

- 规定普通表单字段存在非空控件值时直接采用该值，不再用页面文本覆盖。
- 保留控件值为空时的现有容器和页面文本兜底。
- 明确弹出参照断言比较页面当前显示值，选择时使用的编码不自动拼入期望值。
- 增加失败派生单元测试，并修正开户银行真实回归用例的期望值。

## Capabilities

### New Capabilities

- `form-field-value-reading`: 定义 `form.assert_values` 与 `form.capture_values` 共享的普通表单字段取值优先级和弹出参照显示值语义。

### Modified Capabilities

无。

## Impact

- 运行时：`ydf_browser/runtime.py` 的表单字段读取逻辑。
- 测试：`tests/test_runtime.py` 和开户银行真实回归 DSL。
- 文档：`skills/gov-ydfdev-browser/references/dsl-reference.md` 的表单断言说明。
- 不改变 DSL schema、字段绑定规则或弹出参照选择流程。
