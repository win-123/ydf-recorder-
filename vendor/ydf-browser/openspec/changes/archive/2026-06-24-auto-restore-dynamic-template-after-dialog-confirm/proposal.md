## Why

`执行项目立项` 真实用例在 `设置经费管理员` 弹窗确认成功后，下一步 `query.search(项目名称=...)` 失败为 `未绑定查询字段: 项目名称`。测试人员无法判断哪些 `dialog.confirm` 之后需要手写 `restore_previous: true`，运行时应根据页面实际返回状态自动恢复模板上下文。

## What Changes

- 扩展动态模板恢复规则：`dialog.confirm` 成功关闭由工具栏动作打开的动态模板，并且上一层列表模板可见时，自动恢复上一层模板。
- 保留现有保护：确认后当前动态表单仍暴露稳定动作或字段时，不自动恢复；出现错误通知时也不自动恢复。
- 让 `query.search` 这类非表格后续步骤不再依赖测试人员手写 `restore_previous`。
- 在报告中继续输出 `restored_template` / `auto_restored_template`，便于定位恢复行为。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `dynamic-template-context-restoration`: 扩展 `dialog.confirm` 关闭动态模板并返回列表后的自动恢复要求。

## Impact

- 影响 `ydf_browser/executor.py` 中 `dialog.confirm` 后的动态模板恢复判定。
- 需要补充 executor 层回归测试，覆盖 `toolbar.click` 打开动态弹窗、`dialog.confirm` 更新成功、随后 `query.search` 自动使用列表模板。
- 需要使用真实用例 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-项目库-YDF-82797-0001-执行项目新增父子项目和设置经费管理员new.yaml` 验证不再要求 DSL 显式写 `restore_previous`。
- 不新增 DSL 字段，不引入新依赖。
