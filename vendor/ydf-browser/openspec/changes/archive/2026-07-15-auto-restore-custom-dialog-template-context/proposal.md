## Why

动态编辑页中的自定义业务弹窗动作（例如“去签章”）关闭当前工作面并返回父列表后，executor 仍保留子 manifest，导致后续页签虽然能点击，但表格操作继续按已关闭页面解析。现有自动恢复只覆盖 `保存`、`提交`、`确定`、`确认` 等固定标签，无法处理平台扩展的业务动作。

## What Changes

- 为 `dialog.click` 增加基于运行时 DOM 与 manifest 可见性证据的自定义动作恢复判断。
- 仅在当前动态模板已不再是活动工作面、上一层模板可见且没有错误通知时自动恢复，保持仍活跃表单不被误恢复。
- 在步骤结果中记录自动恢复证据，使报告能区分恢复成功与保留当前模板。
- 补充聚焦回归测试，并用原始真实 DSL 验证“去签章”后的父列表操作。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `dynamic-template-context-restoration`: 扩展 `dialog.click` 的恢复语义，使非固定标签的业务动作也能在运行时证明确已返回上一层时自动恢复模板上下文。

## Impact

- 主要影响 `ydf_browser/executor.py` 的弹窗动作完成后模板恢复判断。
- 需要更新 `tests/test_executor.py`，覆盖自定义动作关闭、当前表单仍活跃和错误通知三类边界。
- 不新增 DSL 字段，不改变显式 `restore_previous` 的现有语义，不引入新依赖。
