## 1. 复现与测试先行

- [x] 1.1 使用 `superpowers:test-driven-development` 梳理附件上传等待行为，并确认当前 `检查工作底稿` 用例的失败报告中 `attachment.upload` 早于业务附件完成。
- [x] 1.2 在 `tests/test_runtime.py` 增加回归测试：`attachment.upload` 在目标附件组件仍为空时不能返回成功，必须继续等待或超时失败。
- [x] 1.3 在 `tests/test_runtime.py` 增加回归测试：上传文件扩展名不符合组件声明的 `enableFileType` / `accept` 时，上传步骤直接失败且不进入后续保存。
- [x] 1.4 在 `tests/test_executor.py` 或报告相关测试中覆盖成功结果包含附件文件和可审计完成证据。

## 2. 运行时修复

- [x] 2.1 调整 `ydf_browser/runtime.py` 的附件根节点解析逻辑，优先使用当前模板中的 `nodeType=upload` / `LCDUploadNext`、`label`、`fieldid`、`divCode` 匹配目标附件组件。
- [x] 2.2 让上传入口定位、文件类型校验、完成等待和诊断采集共享同一个目标附件组件范围，避免全页文本误判。
- [x] 2.3 实现状态驱动等待：上传后持续轮询目标附件组件，直到出现文件名、附件行、附件数量变化或等价业务可见完成信号。
- [x] 2.4 在超时、文件类型不匹配、目标组件不可解析时返回明确错误，并附带诊断文本和截图路径。

## 3. 验证与收尾

- [x] 3.1 运行新增/相关单元测试，确认失败场景和成功等待场景均通过。
- [x] 3.2 使用修改后的 `/Users/ken/temp/ydf-browser-问题反馈/检查工作底稿.yaml` 做真实 CLI 验证，确认 `attachment.upload` 等待完成后再点击 `确定`，最终不再出现 `底稿附件不能为空！`。
- [x] 3.3 运行 `openspec validate fix-attachment-upload-wait --strict`。
- [x] 3.4 运行完整 `./.venv/bin/python -m pytest`，确认全量测试通过。
- [x] 3.5 更新 `tasks.md` 勾选已完成项，并在交付说明中记录真实报告路径和关键 step 证据。
