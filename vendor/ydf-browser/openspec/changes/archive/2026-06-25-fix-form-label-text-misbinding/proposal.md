## Why

`form.fill` 在真实用例“预算支付全景-单位资金/普通转账新增”中把 `收款人全称: 张三` 写进了 `开户银行` 控件，保存时报 `收款人全称不能为空`。根因是运行时采集到串错的 `label_text` 后，绑定层允许“只靠错误 label_text 命中”的前景候选压过更合理的目标字段候选。

## What Changes

- 修正表单字段绑定候选选择：当 runtime 元素自身 `text`、`name` 或等价身份明确指向另一个字段时，不能仅凭串错的 `label_text` 绑定到 DSL 目标字段。
- 保持前景弹窗/抽屉字段优先原则，但要求前景优先不能覆盖字段身份明显冲突的候选。
- 补充回归测试覆盖 `收款人全称` 被 `开户银行` 的 `label_text` 串扰时不能错绑。
- 不新增 DSL 字段，不改变 `form.fill` YAML 写法，不引入新依赖。

## Capabilities

### New Capabilities

### Modified Capabilities
- `form-field-entry`: 表单字段绑定必须排除只靠污染 `label_text` 命中且 runtime 自身文本明确为其它字段的候选。

## Impact

- 主要影响 `ydf_browser/binder.py` 的表单字段候选评分/过滤。
- 回归测试集中在 `tests/test_binder.py`。
- 真实验证使用问题 YAML：`/Users/ken/temp/ydf-browser-问题反馈/功能-单位资金代管-预算支付全景-新增-普通转账-001 (1).yaml`。
