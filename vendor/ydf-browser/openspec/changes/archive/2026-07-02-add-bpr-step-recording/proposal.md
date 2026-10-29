## Why
当前 `ydf-browser` 能按 DSL 执行 YonDiF 页面操作并生成浏览器侧报告，但无法在指定业务动作范围内开启 YonDiF BPR 录制，也无法把 BPR 在线报告链接与 DSL 步骤范围关联起来。测试和开发排障时需要手工开始/结束 BPR，后续分析程序也缺少机器可读的“哪个步骤范围对应哪个 BPR 报告”元数据。

本变更引入显式 `bpr.start` / `bpr.stop` DSL 步骤。本工程只负责 BPR 录制控制和元数据产出，不解析 BPR 报告内容，不存储 BPR 分析结果。

## What Changes
- 新增组件 DSL：`component: bpr`，支持 `operation: start` 和 `operation: stop`。
- BPR 是性能录制能力，只有本次运行开启 `--performance` 时才真实调用 BPR start/stop 接口。
- 未开启 `--performance` 时，BPR 控制步骤直接过滤，不创建 BPR session，不生成 BPR step result、BPR 事件、BPR 报告区块或 `performance.xlsx`。
- 每个 `bpr.start` 与后续第一个 `bpr.stop` 形成一个 BPR session，同一 case 允许多个 session，不支持嵌套。
- `bpr.start` 和 `bpr.stop` 本身不计入录制业务范围；范围只包含二者之间实际执行的业务步骤。
- DSL 加载和语法校验阶段提前拒绝 BPR 嵌套、没有 active session 的 `bpr.stop` 和缺少 `bpr.stop`。
- Playwright runtime 在 start 时写入 BPR cookies，
- `/iuap-ymc-agent/monitor/record`；stop 时调用 `/iuap-ymc-agent/bprcall` 获取在线报告 URL。
- `report.json` 在 case 级记录 BPR sessions 元数据，包括步骤范围、包含步骤、BPR ID、在线报告链接和状态。
- `performance.xlsx` 新增 `BPR录制` sheet，面向后续外部分析程序提供范围、包含步骤和在线链接。
- `report.html` 在 case 详情中展示 BPR 录制范围和在线链接，便于人工打开报告。

## Capabilities
- `bpr-step-recording`: 在 DSL 中显式控制 BPR 局部录制并输出录制元数据。
- `performance-xlsx-report`: 在性能工作簿中导出 BPR 录制 session 清单。

## Impact
- 影响 DSL schema、执行器、Playwright runtime、报告模型、HTML 报告和 Excel 导出。
- 需要新增单元测试覆盖 DSL 静态校验、执行器 BPR 状态保护、runtime start/stop 调用、报告结构和 Excel sheet。
- 不改变现有非 BPR DSL 行为；未开启 `--performance` 时 BPR 步骤不触发实际录制，也不在运行产物中留下 BPR 痕迹。
