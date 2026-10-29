## 1. 回归测试

- [x] 1.1 在 `tests/test_executor.py` 增加回归，覆盖 `table_row_action.click` 直接打开参照模板、`popup_reference.select` 关闭后恢复上一层双表格模板。
- [x] 1.2 运行新增测试并确认修复前因缺少 `auto_restored_template` 或后续表格绑定错误而失败。

## 2. 最小实现

- [x] 2.1 扩展 `popup_reference.select` 后的模板恢复来源，纳入 `table_row_action.click` 并复用现有身份与可见性保护。
- [x] 2.2 运行新增测试及相关动态模板恢复测试，确认行级参照恢复且行级编辑表单保留行为不退化。

## 3. 真实验证与完整回归

- [x] 3.1 用仓库源码运行原始 YAML，确认越过 `物资申请出库信息` 表格名称误判并记录真实结果。
- [x] 3.2 运行完整 pytest、OpenSpec strict 校验、OpenSpec 中文门禁和 `git diff --check`。
