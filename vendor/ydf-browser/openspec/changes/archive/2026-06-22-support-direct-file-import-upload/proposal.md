## Why

`项目期初余额` 新增页里的 `导入` 不是平台公共导入组件，而是 `YDFileImportButton` 普通按钮：点击后直接弹出文件选择器并开始导入。现有 `import.upload` 固定走公共导入工作台，`attachment.upload` 又只适合附件区，导致这类真实页面无法用语义 DSL 稳定表达。

## What Changes

- 扩展 `import.upload` 运行时语义：当目标导入动作绑定到 `YDFileImportButton` 或等价的直连文件导入按钮时，点击按钮并捕获浏览器 file chooser，设置 DSL 提供的文件。
- 保持现有公共导入工作台流程不变；未识别为直连文件按钮时继续走当前 `YDFImportDropdownButton` 下拉导入流程。
- 导入结果仍写入 `data.import_results`，继续支持 `target.assert.status` 和失败原因断言。
- 不新增低层 selector、坐标或 Playwright 脚本字段。

## Capabilities

### New Capabilities
- `import-upload`: 定义 `import.upload` 对公共导入组件和直连文件导入按钮的文件选择、结果等待、报告证据要求。

### Modified Capabilities

## Impact

- 影响 `ydf_browser/runtime.py` 中 `import_upload` 的入口分流和 file chooser 处理。
- 影响 `ydf_browser/executor.py` 的导入结果断言路径，仅在需要传递绑定候选或上下文时做最小调整。
- 影响 DSL 文档、回归测试和真实用例 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-项目预算-YDFJF-2337-0001.yaml`。
