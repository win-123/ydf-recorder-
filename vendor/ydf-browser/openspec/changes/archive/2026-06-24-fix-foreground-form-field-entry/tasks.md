## 1. 回归先行

- [x] 1.1 增加 binder 单元测试，覆盖同 `fieldid` 背景字段和前景弹窗字段同时存在时优先绑定 `in_dialog=true` 可编辑字段。
- [x] 1.2 增加 executor/runtime 单元测试，覆盖 `form.fill` 写入普通文本字段后必须确认回填，未回填时失败并报告字段诊断。
- [x] 1.3 增加日期字段单元测试，覆盖 `YDFDatePicker` 的 `dateformat=YYYY` 年份输入写入和回读确认。

## 2. 实现

- [x] 2.1 调整 manifest 表单字段绑定排序，在普通表单候选中优先选择前景层、可编辑、非表格节点，避免背景同名或同 `fieldid` 节点获胜。
- [x] 2.2 复用 runtime 已有前景表单 root 解析能力，让 `fill_form_field()` 在写入前确认最终 root 属于当前可操作表单上下文。
- [x] 2.3 为普通文本、数字、日期字段增加写后确认逻辑；确认失败时抛出包含字段名、目标值、实际读数和 selector 的错误。
- [x] 2.4 在 `form.fill` 步骤结果中保留每个已确认字段的运行时身份和确认读数，便于后续诊断。

## 3. 验证

- [x] 3.1 运行新增或受影响的最小单元测试。
- [x] 3.2 使用 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-项目库-YDF-81126-0001-财政项目接入.yaml` 或等价临时探针验证 `项目代码`、`项目名称`、`设立年度` 均写入前景新增表单。
- [x] 3.3 运行项目测试套件的相关子集，确认 `form.fill`、choice/dropdown、switch、radio、popup reference 既有能力未回退。
- [x] 3.4 运行 `openspec validate fix-foreground-form-field-entry --strict` 和 `./scripts/check_openspec_language.py --change fix-foreground-form-field-entry`。
