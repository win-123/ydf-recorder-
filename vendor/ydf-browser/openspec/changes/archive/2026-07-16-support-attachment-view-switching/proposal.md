## Why

`attachment.upload` 当前只能操作附件卡片视图；当单据模板默认使用附件表格视图或用户切换到该视图时，运行时无法找到按附件类型展示的上传入口。DSL 表达的是上传业务行为，不应依赖附件组件当前采用哪种视图。

## What Changes

- 运行时按当前可见 DOM 识别附件卡片视图或附件表格视图，模板 `viewType` 仅作为诊断信息。
- 附件表格视图下，整步切换一次到附件卡片视图，复用现有按类型上传和业务完成等待逻辑，结束后恢复原视图。
- 上传失败时仍尝试恢复；恢复失败不覆盖原始上传错误。文件已上传但恢复失败时，步骤失败并明确报告上传结果。
- 步骤报告增加 `initial_view`、`upload_view`、`view_restored`，不增加 DSL 视图配置。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `attachment-upload`: 增加附件视图无关的上传、原视图恢复及视图诊断证据要求。

## Impact

- 修改 `ydf_browser/runtime.py` 的共享附件上传入口和运行时 DOM 交互。
- 补充 `tests/test_runtime.py` 对切换、恢复及失败路径的覆盖。
- 更新附件上传规格和面向使用者的能力说明；不新增依赖，不改变 DSL schema。
