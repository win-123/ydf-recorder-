## 1. 回归测试

- [x] 1.1 增加真实 Chromium DOM 测试，证明视口外 textarea 的 `pointer_receivable` 为未知
- [x] 1.2 增加可编辑表格测试，证明 `ResolvedTableScope.token` 进入新增脚本且验证根只统计目标表格行

## 2. 运行时修复

- [x] 2.1 将完全位于视口外的控件记录为 pointer 未知，并按视口交集采样部分可见控件
- [x] 2.2 在 `editable_table.add_row` 中复用已解析表格作用域 token，并在 token 失效时于点击前失败关闭

## 3. 验证与交付

- [x] 3.1 运行聚焦测试和“相关产业发展情况”最小真实 DSL，确认身份冲突消失
- [x] 3.2 运行成员表真实 DSL，确认新增报告记录目标表格 `1 -> 2` 且验证根来源为 `resolved-table-scope`
- [x] 3.3 运行完整 pytest、`git diff --check`、OpenSpec strict 校验和语言检查
