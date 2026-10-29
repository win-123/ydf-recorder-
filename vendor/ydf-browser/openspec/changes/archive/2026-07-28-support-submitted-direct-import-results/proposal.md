## Why

直连文件导入按钮选择文件后可能只由后端解析并以表格回填、对话框等业务形态呈现结果，不一定出现公共导入进度界面或通知。现有 `import.upload` 在缺少标准结果时固定等待并超时，既无法表达“后端已接收、业务结果另行断言”，也无法覆盖名称和组件类型各异的业务导入按钮。

## What Changes

- 保持公共导入组件和直连文件导入按钮统一使用 `import.upload`，按真实 file chooser 或公共导入界面识别入口形态，不维护按钮名称白名单。
- 允许 `import.upload` 使用 `target.label` 或 `target.fieldid` 绑定名称不同或同名的业务导入动作。
- 为直连导入增加显式 `assert.status: submitted`，表示相关后端上传或解析请求已成功完成，但页面没有提供可识别的业务结果。
- 明确 `success` 可以满足 `submitted`，任何明确的 `failure` 均使步骤失败；未显式期待 `submitted` 时仍默认要求 `success`。
- 要求期待 `submitted` 的导入步骤后存在业务断言，避免用“已提交”冒充业务成功。
- 当前真实用例通过完整表格行值断言验证导入回填；本地文件解析不在本次范围内。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `import-upload`: 扩展直连文件导入的入口识别、后端请求证据、`submitted` 状态、状态兼容规则和后置断言门禁。

## Impact

- 影响 `ydf_browser/runtime.py` 中导入入口识别、直连文件选择和后端请求结果采集。
- 影响 `ydf_browser/executor.py` 中导入期望状态传递与状态断言。
- 影响 `ydf_browser/dsl.py` 中 `submitted` 后置业务断言的跨步骤校验。
- 影响导入 DSL schema、示例、参考文档、运行时、执行器和 DSL 校验测试。
- 需要使用真实 DSL `/Users/ken/temp/ydf-browser-问题反馈/流程-预算执行-转移支付执行-一般资金调度流程-0001.yaml` 验证直连导入和完整表格回填。
