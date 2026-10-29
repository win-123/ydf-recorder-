## 1. 回归测试

- [x] 1.1 在 `tests/test_executor.py` 增加普通 `form.fill` 弹出参照字段 `selected` 但 `confirmed=false` 时必须失败的回归测试。
- [x] 1.2 在 `tests/test_runtime.py` 增加人员类 `YDFReferSelect` 未确认关闭不得成功的运行时回归，覆盖字段未回填且候选层仍可见的场景。
- [x] 1.3 保留并运行既有可编辑表格参照回归，确认 `scalar unique`、候选点击后回填和短超时性能修复不被回滚。

## 2. 运行时修复

- [x] 2.1 调整 `_select_popup_reference()` 的早退结果，区分普通表单字段和可编辑表格单元格参照路径。
- [x] 2.2 对普通表单弹出参照字段，要求确认动作成功、字段真实回填或候选层真实关闭证据；否则抛出包含字段上下文的错误。
- [x] 2.3 调整 `_popup_reference_dialog_hidden_now()` 或其调用方式，避免因快速扫描未命中 `选择面 + 确认按钮` 就把仍可见的人员参照判定为隐藏。
- [x] 2.4 在 `WorkflowExecutor._execute_form_fill()` 中处理 `last_popup_reference_result.confirmed=false` 的普通表单参照结果，避免继续报告 `form.fill success=true`。
- [x] 2.5 在字段结果中补充 `close_action`、回填状态或候选层可见性诊断，便于后续排查绿灯假阳性。

## 3. 真实验证

- [x] 3.1 运行聚焦单测：`./.venv/bin/python -m pytest tests/test_runtime.py tests/test_executor.py -k "popup_reference and confirmed"`.
- [x] 3.2 真实运行 `/Users/ken/temp/ydf-browser-问题反馈/流程-预算管理-项目库-二级项目管理财务-新增-0001.yaml`，确认 `项目联系人` 和 `项目负责人` 不再以 `confirmed=false` 通过。
- [x] 3.3 若修复后真实用例通过，检查报告中两个人员参照字段包含 `confirmed=true` 或等价回填/关闭证据。
- [x] 3.4 运行完整测试：`./.venv/bin/python -m pytest`。

## 4. OpenSpec 门禁

- [x] 4.1 运行 `openspec validate fix-form-popup-reference-confirmation --strict`。
- [x] 4.2 运行 `./scripts/check_openspec_language.py --change fix-form-popup-reference-confirmation`。
