## Why

`预算支付全景-单位资金` 新增普通转账用例中，`结算方式` 模板字段是 `YDFSelect`，但元数据声明 `refuri` 参照信息。当前 runtime 仅按组件名把它当普通下拉处理，导致不打开参照弹窗并报 `未找到查询条件可选值`。

## What Changes

- `form.fill` 识别表单字段时，优先尊重模板元数据中的 `refuri` 参照声明，避免 `YDFSelect + refuri` 被普通 choice 流程截走。
- 对参照或 choice 字段执行录入前，若当前可见字段值已经与 DSL 目标值等价，直接判定该字段录入成功，避免重复打开候选。
- 补充回归测试覆盖 `YDFSelect + dataType=refer` 和默认值已匹配的场景。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `form-field-entry`: 补充表单参照字段判型和已有值幂等录入要求。

## Impact

- 影响代码：`ydf_browser/runtime.py` 的表单字段类型判断与录入前检查。
- 影响测试：`tests/test_runtime.py` 增加最小回归。
- 不新增依赖，不改变 DSL 结构。
