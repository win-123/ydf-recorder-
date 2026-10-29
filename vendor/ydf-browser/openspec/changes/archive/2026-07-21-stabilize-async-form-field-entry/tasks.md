## 1. 回归测试

- [x] 1.1 增加同 `fieldid` 的旧抽屉与当前抽屉同时可见时优先可接收 pointer 实例的失败用例，并先验证测试失败
- [x] 1.2 增加已有绑定为 `in_dialog=true` 时仍重新解析当前前景实例的覆盖

## 2. 运行时实现

- [x] 2.1 在表单字段共享入口按候选身份解析可见且可接收 pointer 的输入根节点
- [x] 2.2 将 pointer 实例解析接入 `fill_form_field()`，并保留无命中时的现有回退链路

## 3. 验证

- [x] 3.1 运行聚焦 runtime 测试、OpenSpec 严格校验和语言检查
- [x] 3.2 运行原始真实 DSL，确认值写入可交互 `proName` 且保存不再报该字段为空
- [x] 3.3 运行完整 `./.venv/bin/python -m pytest` 和 `git diff --check`
