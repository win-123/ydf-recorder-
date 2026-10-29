## 1. 回归测试

- [x] 1.1 新增 executor 回归，验证 `toolbar.click` 打开临时选择模板后 `dialog.confirm` 自动恢复上一层表单模板，后续 `toolbar.click 保存` 可绑定。
- [x] 1.2 新增 executor 回归，验证 `action.click` 打开同类临时选择模板后具备相同行为。

## 2. 实现

- [x] 2.1 调整 `dialog.confirm` 后的模板恢复判断，避免仅因临时选择模板仍有 `确认/取消` 动作而阻止恢复。
- [x] 2.2 保持当前动态表单仍有保存类稳定动作时不自动恢复的既有保护。

## 3. 验证

- [x] 3.1 运行 OpenSpec 结构校验和语言门禁。
- [x] 3.2 运行新增/相关 executor 单元测试。
- [x] 3.3 用真实 DSL 验证 `toolbar.click 选择` 和 `action.click selectInfoBtn` 两种写法。
- [x] 3.4 运行全量 pytest。
