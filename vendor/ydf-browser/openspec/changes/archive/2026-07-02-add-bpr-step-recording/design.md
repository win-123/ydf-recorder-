## Overview
BPR 集成按“显式步骤控制、性能模式启用、工程只产出录制元数据”的原则实现。DSL 作者通过 `bpr.start` 和 `bpr.stop` 精确包裹一个或多个业务步骤。显式 DSL 校验和开启 `--performance` 的运行会在读取 YAML 并构建 case steps 时做 BPR 配对校验，拒绝嵌套、无 start 的 stop 和缺少 stop 的无效 DSL。未开启 `--performance` 的运行会把 BPR 控制步骤当作禁用的性能指令直接过滤，不执行、不校验配对状态、不写入任何运行产物。当本次运行开启 `--performance` 时，执行器维护当前 active BPR session，把 start/stop 之间的业务步骤记录为 session 范围，并在 stop 时调用 runtime 结束录制得到在线报告 URL。

本工程不解析 BPR 报告内容，也不负责 BPR 分析结果持久化。后续分析程序可读取 `report.json` 或 `performance.xlsx` 中的 BPR session 元数据，再访问在线报告链接自行分析。

## Goals
- 支持一个 case 中多段局部 BPR 录制。
- 明确 start/stop 控制步骤不计入业务录制范围。
- 在 DSL 加载和语法校验阶段发现 BPR 嵌套、无 active stop 和缺少 stop，避免进入登录和业务执行阶段。
- 将 BPR 视为性能能力：只有开启 `--performance` 时才真实录制 BPR。
- 输出机器可读的 BPR session 元数据，包括录制范围、包含步骤和在线报告链接。
- 使用浏览器上下文写 cookie 和调用 BPR 接口，复用真实登录态、Referer、Origin 和租户上下文。
- 保持未启用 BPR 的现有运行、报告和性能导出行为不变。

## Non-Goals
- 不解析 BPR HTML 报告内容。
- 不做 BPR 接口耗时、SQL、trace 或后端调用链分析。
- 不支持嵌套 BPR 录制。
- 不在用户漏写 `bpr.stop` 时自动停止录制；这类 DSL 写法应失败并提示。

## Decisions
### DSL 形态
采用组件步骤：

```yaml
- component: bpr
  operation: start
  target:
    name: 修改并取消

- component: toolbar
  operation: click
  target:
    label: 修改

- component: toolbar
  operation: click
  target:
    label: 取消

- component: bpr
  operation: stop
```

`target.name` 可选，仅用于报告展示。第一版不要求 DSL 提供用户 ID、租户 ID、host 等 BPR 参数，这些信息由 runtime 从当前页面、环境配置和用户上下文中采集或使用安全兜底值。

### DSL 静态校验
DSL 加载器完成 YAML 解析、变量替换和 step 规范化后，对每个 case 的 steps 做一次 BPR 配对扫描：

- idle 状态遇到 `bpr.start`：记录当前 open session。
- recording 状态遇到另一个 `bpr.start`：校验失败，提示不支持嵌套 BPR 录制。
- idle 状态遇到 `bpr.stop`：校验失败，提示没有正在录制的 BPR session。
- recording 状态遇到 `bpr.stop`：关闭当前 open session，回到 idle。
- case steps 扫描结束时仍 recording：校验失败，提示缺少 `bpr.stop`。

该校验属于 BPR 启用时的 DSL 语法校验。`ydf-browser validate` 和 `ydf-browser run --performance` 都会在加载 DSL 时触发。失败时不应登录、不应打开菜单，也不应执行任何业务步骤。

`ydf-browser run` 未开启 `--performance` 时，BPR 控制步骤不参与 BPR 配对状态校验。即使 DSL 中的 BPR 控制步骤存在嵌套、无 active stop 或缺少 stop，非性能运行也应忽略这些步骤并继续执行业务步骤。

### 性能开关语义
BPR 是纯性能录制能力，`--performance` 是 BPR 的运行时总开关：

- 开启 `--performance`：`bpr.start` 调用 runtime start，`bpr.stop` 调用 runtime stop，并产出 BPR session 元数据。
- 未开启 `--performance`：`bpr.start` / `bpr.stop` 不调用 BPR runtime 接口，不创建 BPR session，不产出步骤结果、事件、报告区块或跳过记录。
- 未开启 `--performance` 时，即使 DSL 包含 BPR 步骤，也不因为 BPR 单独生成 `performance.xlsx`。
- 未开启 `--performance` 时，`report.json`、`report.html`、`events.jsonl`、stdout 摘要和其它运行产物都不应出现 BPR session、BPR step result、BPR 错误或 BPR 跳过痕迹。

### 执行器状态机
执行器在开启 `--performance` 时维护一个 active session。该状态机负责真实 start/stop 调用和录制范围产出，同时作为内部入口绕过 DSL loader 时的防御性保护：

- idle 状态遇到 `bpr.start`：调用 runtime start，记录 `start_control_step`。
- recording 状态遇到普通业务步骤：步骤执行完成后追加到 active session 的 `actions`。
- recording 状态遇到 `bpr.stop`：调用 runtime stop，记录 `end_control_step`、业务 `start_step/end_step`、在线报告链接，并归档到 case BPR session 清单。
- recording 状态遇到另一个 `bpr.start`：防御性失败，提示不支持嵌套。
- idle 状态遇到 `bpr.stop`：防御性失败，提示没有正在录制的 BPR。
- case 结束时仍 recording：防御性失败，提示缺少 `bpr.stop`。

### Runtime 接入
开启 `--performance` 后，Playwright runtime 按文档推荐方式实现：

- 生成唯一 `bprId` 和毫秒级 `startTs`。
- 通过 `browser_context.add_cookies()` 写入 `mdd_monitor_uid`、URL 编码后的 `ymc_flag`、`mdd_monitor_record`、`ymc_recording`。
- 通过当前页面 `page.evaluate(fetch)` 调用 `/iuap-ymc-agent/monitor/record`，允许该请求失败但记录警告。
- stop 时通过 `page.evaluate(fetch)` 调用 `/iuap-ymc-agent/bprcall`，提交最小 UBA 数据，要求响应中返回 HTTP 在线报告 URL。

### 报告落点
主数据落在 case report：

```json
"bpr_sessions": [
  {
    "index": 1,
    "name": "修改并取消",
    "bpr_id": "ydf...",
    "start_control_step": 1,
    "end_control_step": 4,
    "start_step": 2,
    "end_step": 3,
    "range": "step 2 - step 3",
    "actions": ["2 toolbar.click 修改", "3 toolbar.click 取消"],
    "report_url": "https://...",
    "success": true
  }
]
```

`bpr.start` 和 `bpr.stop` 的 step result 只放当前控制步骤摘要，完整 session 清单由 case report 持有。

### Excel 导出
开启 `--performance` 时，`performance.xlsx` 增加 `BPR录制` sheet。每行对应一个 session，列包含运行 ID、suite、case、BPR 序号、名称、BPR ID、控制步骤、业务步骤范围、包含步骤、在线报告链接、开始结束时间、耗时、状态和错误。未产生 BPR session 时，该 sheet 明确标记无 BPR 录制记录。未开启 `--performance` 时，不因为 DSL 中存在 BPR 步骤单独生成 `performance.xlsx`；若没有其它性能输出需求，则不生成该文件。

## Risks
- BPR 报告生成是异步的，`/bprcall` 返回 URL 时内容可能尚未完全生成；本工程只记录 URL，不等待报告内容完备。
- 如果业务服务没有接入 YMC/APM SDK，或录制期间业务请求未带 BPR cookie，BPR 报告可能缺少后端链路；本工程只保证写入 cookie 和调用接口。
- 如果页面 SDK 必须在加载时读取 cookie，某些场景可能需要 reload；第一版默认不自动刷新页面，避免改变用户业务步骤语义。

## Open Questions
- BPR userId/userName/tenantId 的最佳来源可能需要结合真实接口返回字段进一步确认。第一版可以从当前用户上下文、页面变量或环境配置中按可用性兜底。
- 是否需要在 HTML 报告中为 BPR report URL 做登录态提示，等真实报告访问权限验证后再决定。
