# Proposal

## Why

真实专家库 DSL 编写会话只能发现树参照根节点，最终依赖用户提供末级文本才能保存。参照选择拒绝通知还被通用的弹窗未关闭错误遮蔽，造成重复探索。

## What Changes

- 保持测试 DSL 不变：通过 `--ai-observe` 输出候选证据，通过显式 `--explore-reference` 参数在成功用例结束后探索。
- 不自动全树遍历；候选较多时返回有界结果和继续发现方式，未知可选性不得伪装为可选。
- 参照确认收到拒绝通知时报告真实原因，保留字段与目标证据。
- 技能明确普通测试字段可以在用户允许时选择已观察合法候选；业务分支仍需明确。
- 用同一专家库用例和 `gpt-6-luna max` 独立会话比较，保存后读回两个参照值并清理。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `popup-reference-tree-table-selection`: 增加观察证据、有界探索参数及共享选择拒绝诊断。

## Impact

涉及 CLI、executor、popup_reference 共享入口、技能文档、术语表和测试；不新增依赖，不改变既有选择默认规则，不处理表单必填、菜单歧义或页面整体就绪问题。
