## Context

当前 `import.upload` 只支持平台公共导入组件：点击工具栏导入入口、选择下拉子项 `导入`、在导入工作台中选择文件、点击工作台确认、等待进度弹窗并提取结果。`项目预算>>年末处理>>项目期初余额` 的新增页不同，模板里 `导入` 是 `YDFileImportButton`，`props.justFile=single`，点击按钮后浏览器直接打开 file chooser 并立即触发导入。

`attachment.upload` 不能复用到这里，因为它面向 `LCDUploadNext` 附件区，需要附件类型、组件范围和附件已接受状态。该页面的按钮是表格动作，不是附件区。

## Goals / Non-Goals

**Goals:**

- 保持 DSL 写法为 `component: import` / `operation: upload`。
- 运行时自动识别直连文件导入按钮，并用 file chooser 上传 DSL 文件。
- 公共导入工作台流程保持兼容。
- 成功或失败结果继续写入 `data.import_results`。

**Non-Goals:**

- 不新增 `attachment.upload` 的特殊语义。
- 不要求 DSL 作者提供 selector、坐标、按钮组件名或 Playwright 操作细节。
- 不为每个菜单写页面特例。
- 不改变 `import.download_template` 行为。

## Decisions

### Decision: 复用 `import.upload`，不新增 DSL 操作

`import.upload` 已表达“导入业务文件并等待导入结果”。直连文件按钮只是入口形态不同，不是新的业务概念。继续使用现有 DSL 可以避免把用例写成附件上传或低层浏览器脚本。

备选方案是新增 `import.direct_upload` 或 `mode: direct_file`。当前模板已能暴露 `YDFileImportButton` 和 `justFile=single`，显式 mode 暂时没有必要；如果后续遇到无法从模板识别的普通按钮，再补显式字段。

### Decision: 以模板动作身份触发直连分支

运行时应先按现有工具栏动作绑定找到 `label=导入`。当候选动作的 `component_name` 为 `YDFileImportButton`，或原始模板属性包含 `justFile`，走直连 file chooser 分支；否则保留公共导入工作台分支。

这样可以复用现有工具栏 fieldid、可见性和点击可达性处理，避免全页面裸文本点击误命中。

### Decision: 结果等待复用导入结果采集

直连文件选择后仍应等待页面导入结果。若页面出现已有导入进度弹窗，继续复用 `_wait_for_import_results()` 提取 `success/failure/message`。如果没有可识别结果，步骤必须失败并保留诊断，而不是仅因 file chooser 已设置文件就返回成功。

## Risks / Trade-offs

- 直连按钮可能不显示标准导入进度弹窗 -> 先按真实页面验证；若只有 toast 或表格回填，后续再为 `import.upload` 增加可观察结果信号。
- 多文件按钮能力未知 -> `justFile=single` 页面先支持单文件；多文件保持现有 `files` 输入但以真实 file chooser 能力为准。
- 同名 `导入` 可能同时存在公共导入和直连按钮 -> 优先使用模板绑定到的动作身份，不按全页面文本猜测。
