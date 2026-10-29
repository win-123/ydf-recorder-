## Why

`YDFDateRange` 日期范围控件当前会被 `form.fill` 误当作普通日期输入处理，运行时可能只给外层节点写入 `value/title` 并读回，报告显示已确认，但页面控件实际仍为空，后续保存会触发必填错误。

需要把日期范围字段定义为一等的表单录入语义：DSL 仍表达“字段等于某个起止日期区间”，runtime 必须真实选择或写入控件内部状态，并用真实可见值或业务保存结果证明成功。

## What Changes

- `form.fill` 支持 `YDFDateRange` 字段的标量区间值，格式为 `YYYY-MM-DD~YYYY-MM-DD`，允许分隔符两侧有空格。
- runtime 将 `YDFDateRange` 与普通 `YDFDatePicker` 分开处理，不再把日期范围外层 `div` 的自写属性当作成功确认。
- 字段录入报告需要保留归一化后的实际区间值、目标字段身份和确认结果；未能真实回填时必须失败。
- 更新真实问题用例或新增稳定样例，覆盖 `对账起止日期: "2026-01-01~2026-01-12"` 的写法。

## Capabilities

### New Capabilities

- None

### Modified Capabilities

- `form-field-entry`: 扩展普通表单字段录入契约，明确 `YDFDateRange` 日期范围字段的 DSL 标量语法、真实录入和确认要求。

## Impact

- 影响 `ydf_browser/runtime.py` 的 `form.fill` 日期字段分流、日期范围录入、读值确认和诊断。
- 可能影响 `ydf_browser/template_parser.py` 或绑定逻辑对 `YDFDateRange` 真实输入节点、后缀图标和前景字段根的定位。
- 需要新增或调整 `tests/test_runtime.py`、`tests/test_executor.py`、`tests/test_template_parser.py` 中的窄单测。
- 需要用真实 YAML 验证：`/Users/ken/temp/ydf-browser-问题反馈/功能-电子对账-对账期间设置 - 新增停用启用延期删除批量生成-001.yaml`。
