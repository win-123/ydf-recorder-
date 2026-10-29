## Why

入库审核点击“销审”后只打开工作流操作面板，仍需执行面板中的“撤回审批”才能完成逆向业务流程。当前 DSL 无法表达这个独立动作，原用例会在入口点击后结束，不能证明销审生效。

## What Changes

- 新增 `workflow_panel.click`，以必填 `target.label` 精确指定前景工作流操作面板中的操作项。
- 保留 `toolbar.click` 的现有行为；打开面板和执行操作由两个显式步骤表达，不自动点击后续动作。
- 同时支持平台渲染为按钮和单选式操作项的入口，不把附言、评论、历史或流程图纳入首版。
- 限定面板作用域并检查唯一性、可见性、禁用和遮挡状态；不使用背景同名按钮兜底。
- 等待本次动作的明确完成信号；缺少证据时失败，不使用兼容超时成功。出现标准确认弹窗时交由后续 `dialog.confirm`。
- 在 `data.workflow_panel` 中保存面板、操作项和完成状态证据；真实 DSL 增加销审后业务断言。
- 同步 DSL 校验、schema、能力声明、文档、示例、聚焦测试和真实回归用例。

## Capabilities

### New Capabilities

- `workflow-panel-actions`: 工作流操作面板的作用域识别、显式点击、完成判定和步骤证据。

### Modified Capabilities

无。既有工具栏、标准弹窗、工作流批量结果层和通用兼容等待的语义保持不变；新组件使用专用完成约束。

## Impact

- `ydf_browser/dsl.py`、`schemas/dsl.schema.json`：新组件和严格目标校验。
- `ydf_browser/executor.py`、`ydf_browser/runtime.py` 及相关动作等待入口：分派、面板定位、完成判定、通知与模板转换。
- 观察能力注册：声明 `workflow_panel`，仅实际使用时启用。
- `CONTEXT.md`、DSL 文档、配套 skill 参考、示例和 `tests/real_cases/`：统一术语和用户用法。
- 不增加依赖，不修改被测业务系统，不写入真实配置、凭据或运行报告。
