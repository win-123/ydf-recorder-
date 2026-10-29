## Why

真实采购计划用例在行编辑表单打开、表单确认关闭和保存确认框打开后仍等待数秒至数十秒。报告与最小检查表明：已应用模板后重复等待新模板、表单模式仍等待行数增长，以及精确前景迁移未接入共享动作完成判定，是工具侧延迟而非业务接口耗时。

## What Changes

- 已应用的表单模板不再触发无条件的新模板等待；保留尚未完成的动态模板切换处理。
- 新增行打开编辑表单后停止无意义的行数轮询，不重复点击；仍由模板就绪证据裁决成功。
- 共享点击入口记录本次动作的精确工作面，识别源弹窗关闭及新确认框可交互，及时交接后续步骤。
- 确认框就绪只表示等待后续确认，不表示保存成功；保持通知优先级、错误处理、下载协议及证据不足时的兼容超时。
- 补充最小回归检查并用原真实 DSL 对比等待耗时，不改变 DSL 字段或要求用例添加绕过逻辑。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `dynamic-template-context-restoration`: 已就绪表单避免重复等待，待处理动态模板仍先应用再录入。
- `editable-table-cell-entry`: 行编辑表单出现后不继续等待表格即时增行或再次点击新增。
- `runtime-action-completion-signals`: 精确动作源弹窗关闭与确认框交接的完成判定及报告边界。

## Impact

影响 `ydf_browser/runtime.py`、`ydf_browser/executor.py`、`ydf_browser/template_restoration.py` 的共享调用链、相关测试和完成信号文档。不增加依赖，不修改登录、业务数据选择、业务保存接口或 DSL schema。真实验证沿用已有测试草稿用例，不提交业务单据。
