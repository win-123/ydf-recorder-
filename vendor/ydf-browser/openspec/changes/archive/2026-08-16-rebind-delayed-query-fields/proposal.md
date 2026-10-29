## Why

YonDiF 页签在报告 `tab_active` 后仍可能继续渲染查询输入；当前 executor 只在页签步骤结束时绑定一次，若输入稍后出现，紧接的 `query.search` 会错误报告“未绑定查询字段”。该问题已在“专家库新增保存后按专家姓名查询”真实链路中复现，需要在共享查询入口修复而不是依赖重新打开菜单。

## What Changes

- 当当前 manifest 明确声明目标查询字段、但现有 binding 尚未包含该字段时，`query.search` 在失败前限时刷新当前 manifest binding。
- 保留编辑表单上下文中的防误绑规则：不存在 manifest 查询字段时，不得把同名普通表单字段当作查询字段。
- 增加覆盖“页签绑定快照之后查询输入才出现”的 executor 回归测试，并用原真实 DSL 验证新增保存后的查询链路。
- 不在本 change 中处理 `action.click` 打开参照时的模板恢复判断；该问题与查询字段是否及时绑定是独立缺陷。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `query-popup-reference-selection`: 补充普通查询字段延迟渲染时的 manifest-aware 重新绑定要求，并保持查询字段与编辑表单字段的作用域隔离。

## Impact

- 运行时代码：`ydf_browser/executor.py`
- 回归测试：`tests/test_executor.py`
- 主规格：`openspec/specs/query-popup-reference-selection/spec.md`
- 无 DSL schema、命令行参数、依赖或报告结构变更。
