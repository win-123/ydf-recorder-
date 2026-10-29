## 1. 回归测试先行

- [x] 1.1 在 `tests/test_runtime.py` 添加失败回归：`LCDEnum` / `enumType` 表单字段即使根节点包含下拉箭头，也必须调用 `_select_query_choice()`，不得调用 `_select_popup_reference()`。
- [x] 1.2 添加边界回归：`YDFTableModalSelect` / `YDFTreeModalSelect` 仍走 popup reference，表格参照标量值仍触发现有结构化 match 校验。
- [x] 1.3 运行新增聚焦测试，确认修复前能复现分支错误或修复后覆盖到目标分支。

## 2. 运行时实现

- [x] 2.1 扩展 `ydf_browser/runtime.py` 中普通 choice 字段识别逻辑，支持 `LCDEnum` 组件名。
- [x] 2.2 扩展同一识别逻辑，支持模板 raw 元数据中的非空 `enumType` / 等价枚举类型声明。
- [x] 2.3 确保 switch、radio、date 和明确 modal reference 的判断优先级不被改变。
- [x] 2.4 确保普通枚举字段失败时进入 choice/dropdown 诊断路径，而不是 popup reference 弹窗缺失路径。

## 3. 验证

- [x] 3.1 运行相关单元测试：`tests/test_runtime.py` 中新增测试及既有 select、radio、switch、popup reference 相关测试。
- [x] 3.2 真实运行 `/Users/ken/temp/ydf-browser-问题反馈/实物管理-易耗品物资-入库填报-新增-0001.yaml`，确认第 3 步 `来源方式: 采购` 不再因 `未打开弹出参照选择框` 失败。
- [x] 3.3 如真实用例越过当前失败点后出现后续独立失败，在报告中记录新的失败步骤并明确它不属于本 change 的根因。
- [x] 3.4 运行仓库完整测试套件，确认所有测试通过后再报告完成。

## 4. OpenSpec 收口

- [x] 4.1 运行 `openspec validate --change support-lcdenum-form-choice` 或项目等价校验命令，确认 artifacts 可解析。
- [x] 4.2 更新 `tasks.md` 勾选已完成任务，并在最终交付说明中附上单测、真实用例和完整套件证据。
