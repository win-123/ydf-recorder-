## Why

YonDiF 的非 `iuap` 工作流批量操作可能展示一个包含总数、成功数、失败数以及“确认”“查看详情”入口的工作流批量结果层。它不是标准弹窗或普通页面提示，当前 DSL 无法结构化观察、断言、采集失败明细或关闭该结果层，容易把真实业务失败误判为验证阻断或静默忽略。

## What Changes

- 新增独立的 `workflow_result` DSL 组件，提供 `assert`、`details` 和 `confirm` 三个操作。
- 支持使用 `total`、`succeeded`、`failed` 结构化整数断言结果层统计，并在步骤报告中写入 `data.workflow_result`。
- 识别结果层时组合可见结果语义、统计信息和操作入口，不仅依赖 `.error-content` 类名。
- `details` 打开内层详情弹窗并采集可见失败明细；详情弹窗继续使用现有 `dialog.confirm` 关闭。
- `confirm` 点击并验证外层结果层实际消失；三个操作复用现有步骤超时和语义轮询。
- 结果层断言预期与实际复用现有业务断言回执；统计不符合预期时沿用现有断言失败语义并保留证据。
- 全部成功时继续使用现有 `notification.assert`，不伪造不存在的结果层。
- **BREAKING**: 运行中真实出现工作流批量结果层而 DSL 未声明对应 `workflow_result` 步骤时，不再允许静默忽略。
- 补充 schema、示例、聚焦测试和真实 DSL 验证覆盖，并声明对应能力。

## Capabilities

### New Capabilities

- `workflow-batch-result-layer`: 定义工作流批量结果层的识别、结构化断言、失败明细采集、分层关闭和报告语义。

### Modified Capabilities

- `ai-development-observation-contract`：将 `workflow_result.assert` 纳入成功和失败业务断言回执范围，并保持 `import.upload target.assert` 不替代后置业务断言的边界。

## Impact

- DSL 解析与 schema：`ydf_browser/dsl.py` 及相关示例。
- 执行与报告：`ydf_browser/executor.py`、`ydf_browser/runtime.py`、观察契约和步骤结果数据。
- 测试：DSL 校验、executor/runtime 聚焦测试和真实工作流 DSL 用例。
- 不修改 YonDiF 前端；能力仅针对前端已经存在的工作流批量结果层。
