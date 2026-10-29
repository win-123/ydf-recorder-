## Why

`attachment.upload` 当前会在文件刚设置到上传控件后过早返回成功，后续 `toolbar.click 确定` 可能早于 YonDiF 业务侧完成附件入库和附件行回填，导致保存校验仍提示“底稿附件不能为空！”。这会让真实用例出现“上传步骤成功但保存失败”的假阳性链路，影响附件类页面的稳定自动化。

## What Changes

- 为 `attachment.upload` 明确“上传完成”的业务成功标准：必须等对应附件组件内出现可证明附件已被接受的文件行、文件名、附件计数或等价状态后才进入下一步。
- 附件上传等待必须限定在目标附件组件或可识别的上传区域内，避免被页面其他文本、按钮文案或后台区域误导。
- 当上传文件类型不符合页面声明的附件类型限制，或目标附件未在超时时间内被业务侧接受时，`attachment.upload` 应失败并输出诊断，而不是继续执行保存。
- 保持 DSL 语义不变，继续使用现有 `component: attachment`、`operation: upload` 和 `target.attachments[].type/file` 写法。

## Capabilities

### New Capabilities

- `attachment-upload`: 定义 YonDiF 附件组件上传的 DSL 语义、完成判定、失败诊断和真实用例验证要求。

### Modified Capabilities

- 无。

## Impact

- 影响运行时附件上传实现，主要涉及 `ydf_browser/runtime.py` 中附件入口定位、文件类型校验、上传完成等待和诊断采集逻辑。
- 影响 executor/report 层对 `attachment.upload` 结果的可信度，但不改变 DSL schema 和用户已有写法。
- 需要补充单元测试覆盖“上传未完成不能提前成功”“文件类型不匹配应失败”“等待目标附件组件完成后再继续”的行为，并用真实 `检查工作底稿` 用例验证。
