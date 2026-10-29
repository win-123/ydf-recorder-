## Why

普通页面树控件在存在搜索框时，当前 `tree.select` 仍会逐个展开折叠节点查找目标值。对于节点量大的 YonDiF 树，这会导致真实用例执行非常慢，甚至在超时前找不到明明可通过搜索定位的节点。

## What Changes

- 为普通页面树选择增加“搜索优先”的定位能力：当解析到目标树区域内存在可用搜索框时，先输入目标标签或值缩小候选范围。
- 搜索后仍按现有树节点点击规则选择目标节点，包括优先点击 checkbox/radio 选择控件、避免重复反选已选节点。
- 搜索不可用、搜索无结果或搜索后仍找不到目标时，继续回退到现有逐级展开查找逻辑。
- 步骤结果或诊断中记录是否使用树搜索以及解析到的树区域，便于排查慢查找和误选问题。
- 不处理本次反馈中的 `对象编码` 表单字段绑定问题，该问题另行建 change。

## Capabilities

### New Capabilities
- `tree-search-selection`: 描述普通页面 `tree.select` 在树控件带搜索框时的搜索优先选择语义、回退行为和诊断要求。

### Modified Capabilities

## Impact

- 影响普通页面树选择运行时：`PlaywrightRuntime.click_tree_node` / `select_tree_node` 及树区域 scoped 查找。
- 可能复用或抽取现有弹出参照树搜索逻辑，但不改变弹出参照树表选择语义。
- 需要新增针对树搜索优先、搜索失败回退、多选树幂等选择的最小回归测试。
- 真实验证目标用例：`/Users/ken/temp/ydf-browser-问题反馈/business_object_create (2).yaml` 至少应越过 `tree.select label=流程管理`。
