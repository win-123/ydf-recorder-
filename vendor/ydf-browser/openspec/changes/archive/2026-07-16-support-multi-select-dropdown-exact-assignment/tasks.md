## 1. DSL 契约与回归测试

- [x] 1.1 先补充失败测试，覆盖普通多选下拉标量、无序列表、空列表和重复值错误，并保留弹出参照列表与普通单选下拉兼容行为。
- [x] 1.2 更新 `COMPONENT_TARGET_SCHEMAS`、DSL 示例和 `tests/test_dsl.py`，让用户可见语义与校验规则一致。

## 2. 共享运行时精确赋值

- [x] 2.1 在普通 choice 共享入口识别运行时多选形态，规范化目标集合，并按唯一候选项身份读取当前已选集合。
- [x] 2.2 实现“当前集合已匹配则跳过，否则清空或定向取消额外项、再选择目标项”的最小同步流程，并支持空集合清空。
- [x] 2.3 在候选歧义、重复目标、无法移除默认项、目标缺项或额外项时失败，同时保持普通单选和弹出参照既有分流。
- [x] 2.4 补充 `tests/test_runtime.py` 聚焦测试，覆盖 WUI/Ant/UUI 已选标签、checkbox 选中态、清空入口、候选身份等价和最终集合差异。

## 3. 执行结果与结构化报告

- [x] 3.1 让查询区、表单和可编辑表格透传多选结果，成功记录 `expected_values`、`actual_values`，失败补充 `missing_values`、`unexpected_values`。
- [x] 3.2 补充执行器和报告测试，证明三个录入入口都以完整集合决定成功或失败，而不是仅检查某个目标文本出现。

## 4. 验证与真实用例

- [x] 4.1 运行 DSL、runtime、executor 相关聚焦 pytest，修复同一共享入口的相邻回归。
- [x] 4.2 使用当前源码运行 `/Users/ken/temp/ydf-browser-问题反馈/功能-基础信息-账户管理-财政账户信息库-删除-0001.yaml`，确认 `账户状态=草稿` 的报告实际集合不再包含默认“启用”。
- [x] 4.3 运行完整 `./.venv/bin/python -m pytest`、`openspec validate support-multi-select-dropdown-exact-assignment --strict`、`./scripts/check_openspec_language.py --change support-multi-select-dropdown-exact-assignment` 和 `git diff --check`。
