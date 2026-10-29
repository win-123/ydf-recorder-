## 1. Reproduction And Guard Tests

- [x] 1.1 用原始 YAML 复现当前失败，保存报告并确认失败点仍为 `editable_table.fill_row` 的 `汇款转账.收款方户名`，且错误包含误用背景 `关联单据/借款信息` 文本的诊断。
- [x] 1.2 为 `tests/test_runtime.py` 增加失败回归：`YDFReferSelect` 可编辑表格列使用 `{filter, first_available}` 时，如果没有真实候选参照根，运行时必须失败在当前字段弹层解析，不能把背景编辑页当候选根。
- [x] 1.3 为 `tests/test_runtime.py` 增加候选根复用边界回归：`reuse_existing_dialog=True` 只能复用包含有效候选选择面的参照层，不能复用外层业务表单、业务助手、普通内容卡片或已关闭旧弹层。
- [x] 1.4 保留或补充最近相关能力的非回退测试断言：结构化对象不字符串化、树表 `tree + first_available` 右表行优先、`tree + match`、`match.contains`、iframe `保存` 确认、前景业务弹窗内嵌套参照。

## 2. Runtime Fix

- [x] 2.1 调整 `_select_popup_reference()` 的弹层打开/复用逻辑，先验证可复用对象确实是候选参照根；验证失败时必须点击当前字段触发器打开新候选层。
- [x] 2.2 收紧候选参照根识别：背景页面、外层业务表单、普通内容卡片和业务助手即使包含表格、树、保存/取消按钮，也不能在缺少有效候选选择面时被认定为候选根。
- [x] 2.3 在可编辑表格结构化参照失败路径中区分“候选层未打开/未解析”和“候选层内找不到目标值”，并输出表格名、行号、列名、字段组件、目标值、页面摘要和截图诊断。
- [x] 2.4 保持合法嵌套参照兼容：外层业务弹窗内字段打开的内层候选参照仍可被识别、选择、确认，并在关闭后恢复外层业务弹窗上下文。

## 3. Verification

- [x] 3.1 运行新增/受影响的单元测试，例如相关 `tests/test_runtime.py` 和必要的 `tests/test_executor.py` 用例，确认新回归先失败后通过。
- [x] 3.2 运行原始真实 YAML：`./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/功能-网上报销-报销管理-还款单填报-按钮-0011.yaml --headless --report-file /tmp/ydf-repayment-0011-after-fix.json`，确认第 7 步 `收款方户名` 参照打开、选择并回填；如果后续保存因业务校验失败，报告中必须能证明第 7 步已成功越过。
- [x] 3.3 运行最近相关真实或样例回归，至少覆盖物资分类结构化参照、树表 `first_available`、树表 `match/contains`、iframe 保存确认和前景弹窗内嵌套参照中可本地执行的用例。
- [x] 3.4 运行 `openspec validate fix-editable-refer-first-available-dialog-resolution --strict`。
- [x] 3.5 运行完整测试套件 `./.venv/bin/python -m pytest`，全部通过后才能报告实现完成。
