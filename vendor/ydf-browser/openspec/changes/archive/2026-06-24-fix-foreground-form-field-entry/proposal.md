## Why

`财政项目接入` 新增页真实用例中，`form.fill` 报告成功，但前景新增表单里的 `项目代码`、`项目名称` 没有写入。根因是同一页面存在背景/详情区同名或同 `fieldid` 字段，当前绑定优先命中非前景节点，且填充后没有确认目标字段真实回填。

## What Changes

- 让普通 `form.fill` 在存在前景弹窗、抽屉或动态表单时优先绑定当前前景层内可见、可编辑、非表格字段。
- 对 `fieldid`、`dataField` 或标签匹配到多个运行时节点的字段，要求前景层候选优先于背景页候选。
- 对文本、数字、日期等普通表单字段增加写后确认；未读回目标值时步骤必须失败并保留可诊断信息。
- 保留现有 switch、radio、choice/dropdown、popup reference 的专门录入语义，只补齐它们进入普通字段前的上下文选择和成功判定。

## Capabilities

### New Capabilities
- `form-field-entry`: 定义普通表单字段在 `form.fill` 中的前景层绑定、背景字段排除和写后确认语义。

### Modified Capabilities

## Impact

- 主要影响 `ydf_browser/binder.py` 中 manifest 字段与运行时元素的匹配排序。
- 影响 `ydf_browser/executor.py` / `ydf_browser/runtime.py` 中 `form.fill` 的字段解析、录入结果判定和报告数据。
- 需要补充单元测试覆盖前景弹窗字段优先、背景同 `fieldid` 不误填、写后未回填失败。
- 需要用 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-项目库-YDF-81126-0001-财政项目接入.yaml` 或等价临时探针做真实验证。
