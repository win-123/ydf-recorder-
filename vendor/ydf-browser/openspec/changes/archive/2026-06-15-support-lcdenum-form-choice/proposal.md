## Why

真实用例 `/Users/ken/temp/ydf-browser-问题反馈/实物管理-易耗品物资-入库填报-新增-0001.yaml` 在新增页执行 `form.fill` 填写 `来源方式: 采购` 时失败。页面实际字段是 `LCDEnum` 普通枚举下拉，候选中已有 `采购`，但运行时把下拉箭头误判为弹出参照触发器，转入 popup reference 流程并报 `未打开弹出参照选择框`。

这个问题会影响所有使用 `LCDEnum` / `enumType` 渲染普通表单选择项的 YonDiF 页面；DSL 写法本身是语义正确的，不应要求用例作者改写为弹出参照或页面特定 workaround。

## What Changes

- 将普通表单枚举选择控件纳入 `form.fill` 的 choice/dropdown 录入语义。
- 明确 `LCDEnum` 或声明 `enumType` 的表单字段 SHALL 优先按普通下拉候选选择处理。
- 防止普通下拉箭头被误识别为弹出参照触发器，从而避免错误进入 popup reference 流程。
- 保持已有 `YDFSelect`、`YDFTreeSelect`、`YDFRadio`、`YDFSwitch`、`YDFTableModalSelect` 和 `YDFTreeModalSelect` 行为兼容。
- 补充单元回归和真实用例验证，确认 `来源方式: 采购` 能越过当前失败点。

## Capabilities

### New Capabilities
- `form-choice-field-entry`: 覆盖普通表单选择/枚举控件在 `form.fill` 中的识别、候选选择、参照边界和诊断要求。

### Modified Capabilities
- 无。

## Impact

- 主要影响 `ydf_browser/runtime.py` 中表单字段类型判断和下拉选择分支。
- 可能补充 `tests/test_runtime.py` 中对 `LCDEnum` / `enumType` 字段的回归测试。
- 需要真实运行目标 YAML 验证当前失败点已解除；如后续步骤暴露独立业务问题，应在报告中区分。
- 不改变 DSL schema，不新增依赖，不改变 popup reference 的结构化写法。
