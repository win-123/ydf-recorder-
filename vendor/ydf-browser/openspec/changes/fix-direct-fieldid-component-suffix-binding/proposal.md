## Why

多个页面的可见表单下拉、树型选择和日期字段在 `form.fill` 中被排除为 `not_bound`，随后报“平台精确身份状态不兼容”。共同根因是模板节点自身的直连身份没有生成对应的组件子控件后缀候选，导致 binder 无法把外层精确身份收敛到唯一的真实输入。

## What Changes

- 修正表单项直连身份推导：节点自身 `fieldid` 或 `divCode` 优先于“父容器 + dataField”命名约定。
- 为平台直连身份生成已知组件后缀族，覆盖 `YDFSelect` 与 `YDFTreeSelect` 的 `_input`、`_suffix` 和 `_search_input`，以及 `YDFDatePicker` 的 `_input` 和 `_suffix`。
- 保持大小写敏感匹配，不通过归一化大小写掩盖模板与运行时身份差异。
- 保持同根唯一后代控件收敛、前景、可见性、可编辑性和 pointer 校验不变；多个真实控件仍必须保持身份歧义。
- 将资金补录保存成功弹窗步骤中的 `关闭` 目标对齐为页面实际存在的 `取消` 按钮；不调整业务断言或流程顺序。
- 补充 parser、binder 和执行语义测试，并用收入分成管理费配置、单位资金补录结算方式、二级项目项目目录、外贷债权关账日期四个目标控件场景做真实验证。

## Capabilities

### New Capabilities

### Modified Capabilities

- `fieldid-rule-based-location`: 明确节点自身直连身份的优先级，以及直连身份可派生的组件后缀族和同根唯一控件收敛约束。

## Impact

- 影响 `ydf_browser/template_parser.py` 的运行时身份候选生成。
- 影响 `ydf_browser/binder.py` 对平台精确身份和同根后代控件的收敛输入。
- 影响 `form.fill` 对普通下拉、弹出参照和树型选择字段的绑定前置路径；三类字段的既有录入语义不变。
- 需要同步补充聚焦 pytest、OpenSpec 校验和四个受影响 DSL 的真实回归证据；资金补录 DSL 的来源哈希需随文案对齐更新。
