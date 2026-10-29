## 1. 测试先行

- [x] 1.1 为 `PlaywrightRuntime.import_upload` 增加直连文件导入按钮单测，覆盖 `YDFileImportButton` 或 `justFile=single` 时点击按钮、捕获 file chooser、设置文件，并且不打开公共导入工作台。
- [x] 1.2 增加兼容性单测，覆盖普通公共导入组件仍走现有导入工作台流程。
- [x] 1.3 增加 executor 层单测，确认 `import.upload` 对直连导入仍返回 `data.import_results` 并执行 `target.assert`。

## 2. 运行时实现

- [x] 2.1 在导入执行路径中复用现有工具栏动作绑定，识别 `YDFileImportButton`、`raw.props.justFile` 或等价直连文件导入候选。
- [x] 2.2 为直连文件导入实现 file chooser 上传分支，复用现有文件路径校验和可点击动作定位，不使用全页面裸文本点击。
- [x] 2.3 直连上传后复用或扩展现有导入结果等待逻辑，无法识别业务结果时失败并保留诊断截图。

## 3. 文档和真实验证

- [x] 3.1 更新 DSL 文档，说明 `import.upload` 同时支持公共导入组件和直连文件导入按钮，`attachment.upload` 仍只用于附件区。
- [x] 3.2 将 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-项目预算-YDFJF-2337-0001.yaml` 的导入步骤改回 `import.upload` 写法并执行真实用例。
- [x] 3.3 运行 `openspec validate support-direct-file-import-upload --strict`、`./scripts/check_openspec_language.py --change support-direct-file-import-upload`、`./.venv/bin/python -m pytest`。
