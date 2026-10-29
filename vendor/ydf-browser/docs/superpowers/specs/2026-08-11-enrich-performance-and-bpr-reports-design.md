# 增强性能工作簿与 BPR 报告处理设计

## 背景与目标

`ydf-browser run --performance` 已生成 `performance.xlsx`，步骤总览包含动作耗时、请求数量、下载量等指标，BPR 录制页签则只保存在线报告链接和毫秒时间戳。本次变更在不改变业务 DSL 和业务执行结果语义的前提下补充以下能力：

- 步骤总览增加请求上传量和步骤结束时的页面 JS 堆已用量。
- 使用独立凭据下载每段 BPR 的原始 HTML 文件，并保存到本次运行的报告目录。
- 从 BPR 文件中提取用户可见的“服务端概要”，追加到 `BPR录制` 页签。
- 将 BPR 开始、结束时间显示为带本地时区偏移的可读时间，同时保留原始 epoch 毫秒值。

不新增 DSL 字段，不修改轻量执行计时、Web Vitals、业务用例成功判定或 CLI 退出码。暂不支持可插拔认证、动态概要列、BPR 内部文件接口、页面内存峰值采样或严格下载模式。

## 术语与决策

本次在 `CONTEXT.md` 中补充性能采集、性能工作簿、BPR 录制、BPR 报告文件、BPR 服务端概要和报告目录，并通过以下 ADR 固化难以逆转的边界：

- ADR 0013：BPR 报告下载凭据与业务登录凭据分离。
- ADR 0014：BPR 报告文件按下载原文保留，但作为敏感报告产物限制权限和传播。

## 方案选择

采用运行结束后统一增强 BPR 报告的方案。业务 DSL 全部执行完成后、生成 `performance.xlsx` 前，工具使用一组独立凭据登录一次，在一个隔离浏览器上下文中顺序下载所有 BPR 文件、提取服务端概要并回填 session。

不在 `bpr.stop` 中立即下载，因为认证、报告生成等待和文件下载会污染步骤耗时，并在多段录制时重复登录。不调用未公开的 BPR 文件接口；加载报告页面后只读取 `window.pageData?.bprBaseInfo?.bprId` 校验 session 身份，最终仍以真实 download 事件证明文件下载。

数据流如下：

```text
业务 DSL 执行
  -> 生成含 BPR 在线链接的运行结果
  -> BPR 后处理
       -> 独立凭据登录
       -> 隔离浏览器批量下载原始 HTML
       -> 标准库解析服务端概要
       -> 回填 BPR session 状态和字段
  -> 生成 performance.xlsx
  -> 写 report.json / report.html
```

## 代码边界

- `ydf_browser/config.py`：解析环境级可选 BPR 凭据并校验完整性。
- `ydf_browser/runtime.py`：复用现有浏览器、Cookie 和下载能力，增加真实 BPR 报告下载动作。
- `ydf_browser/bpr_report.py`：新增小型函数模块，负责遍历 session、批量后处理和标准库 HTML 解析；不新增接口、工厂或依赖。
- `ydf_browser/cli.py`：在运行结果完成后、性能工作簿导出前调用一次 BPR 后处理入口。
- `ydf_browser/performance_xlsx.py`：只消费已回填的数据，不负责认证、下载或解析。
- `ydf_browser/report_html.py`：同时展示本地 BPR 文件和在线报告链接。

## 配置契约

BPR 凭据位于每个环境的独立节点，真实值只保存在本机 `env.local.yaml`：

```yaml
environments:
  ydf:
    bpr:
      username: bpr-user
      password: bpr-password
```

两项均缺失时允许业务运行，BPR 下载标记为 `not_configured`。只配置其中一项属于配置错误，必须在启动浏览器前停止。BPR 登录地址只取首个合格 `bpr.stop` 返回 `report_url` 的 origin，并通过未改写的原始链接发现同源 CAS 登录页；不使用或回退业务 `base_url`，也不复用业务用户登录态。

BPR 用户名、密码不得进入 DSL、报告、性能工作簿、事件、错误文本或文件名。提交的配置示例只能包含占位值。

## BPR 下载与文件布局

一次运行只建立一个 BPR 登录会话和隔离浏览器上下文。每个 session 在 60 秒总期限内等待页面中的 BPR ID 与 session 一致，且“下载”按钮可见可用；随后捕获 Playwright download 事件并点击真实下载按钮。`report_url` 的 `pk` 是报告记录键，可以与 session BPR ID 不同；只有加载后的 `window.pageData?.bprBaseInfo?.bprId` 用于 session 身份校验。认证不做隐藏的无限重试，60 秒期限不增加为新配置项。

下载成功后文件保存为：

```text
artifacts/<suite>/<case>/bpr/<index>-<bpr_id>.html
```

真实下载先写入最终目录下权限为 `0700` 的私有临时目录，临时文件设为 `0600` 后再原子移动到最终路径；失败自动清理且不发布部分文件。JSON 和 Excel 保存绝对文件路径，HTML 报告生成相对链接，以便整体移动报告目录后仍可打开。BPR 文件不是失败诊断文件，不进入 `diagnostic_files`。

原始 BPR HTML 不做内容改写，不在控制台输出文件内容，也不得进入版本控制。报告核心 DOM 可以离线读取，但工具不承诺文件中的所有外部脚本离线可用。

## BPR session 数据契约

保留现有 `report_url`，并增加：

```text
report_file
download_status
download_error
summary_status
summary_error
server_summary
```

状态枚举为：

- `download_status`: `not_configured | downloaded | failed`
- `summary_status`: `not_attempted | parsed | partial | failed`

下载或解析失败只记录阶段和安全错误摘要，不记录凭据、响应正文或 BPR 文件内容。失败不改变业务用例状态、运行 `success`、CLI 退出码、已取得的在线链接或已下载的原始文件。

## 服务端概要解析

解析器使用 Python 标准库 `HTMLParser` 流式读取 UTF-8 HTML，定位 `#summary-posi`，按首行 `th/td[data-field]` 提取当前 BPR 页面展示的 14 项值。不执行内嵌 JavaScript，不解析 `pageData`，不依赖 `bs4`、`lxml` 或未公开接口。

| 来源字段 | Excel 列 |
|---|---|
| `totalCostTime` | 服务端耗时(ms) |
| `appCostTime` | 计算耗时(ms) |
| `totalRedisCostTime` | Cache耗时(ms)/次数 |
| `totalSqlCostTime` | SQL耗时(ms)/次数 |
| `totalReadrResultTime` | 读结果集耗时(ms)/结果集 |
| `totalThreadNum` | 异步任务数 |
| `totalRpcNum` | RPC次数 |
| `totalRuleCostTime` | Rule耗时/数量 |
| `readFromClientTime` | 上行网络耗时(ms) |
| `writeToClientTime` | 下行网络耗时(ms) |
| `readFromClient` | 上行流量(bytes) |
| `readFromServer` | 下行流量(bytes) |
| `notClosedConnecttion` | 未关闭连接数 |
| `errorSize` | 错误日志数 |

值保持用户可见文本，包括 `耗时 / 次数` 组合值。14 项齐全为 `parsed`；至少取得一项但有缺失为 `partial`；找不到概要或解析异常为 `failed`。未来出现的未知字段先忽略，缺失字段留空，不动态改变工作簿列结构。服务端概要不完整不阻止保存原始文件。

## 上传量采集

每个网络请求完成或失败时按以下顺序取得请求体大小：

1. Playwright `request.sizes().requestBodySize`
2. 已有请求体字节的长度
3. 请求 `Content-Length`
4. `GET/HEAD` 明确记为 0
5. 仍无法确定则标记不可用

只保存字节数，不保存请求体内容。请求按启动步骤归属，与现有请求数量和下载量的因果语义一致。步骤上传量是所属请求体大小之和；任一相关请求无法测量时，Excel `上传KB` 留空，JSON 保存状态和原因。底层报告保留字节整数，KB 换算只在 Excel 导出层完成。

## 页面内存采集

性能模式在每个实际执行步骤结束后读取顶层页面的 `performance.memory.usedJSHeapSize`。采集覆盖成功步骤、失败步骤和 BPR 控制步骤；没有页面、页面关闭或浏览器不支持时不抛出业务异常，Excel 留空，JSON 保存状态和原因。

Excel 列名为 `JS堆已用(MB)`，保留两位小数。该值不是页面内存峰值、步骤增量、跨进程 iframe 总量或浏览器进程 RSS。采集发生在动作耗时停止计时之后，不把指标读取开销计入步骤耗时。

步骤总览的相关列排列为：

```text
上传KB | 下载KB | JS堆已用(MB) | 最慢请求
```

## 时间和工作簿

`report.json` 中保留 BPR 的 Unix epoch 毫秒值。`BPR录制` 页签增加带运行机器本地时区偏移的可读时间，例如 `2026-08-11 17:01:26.352 +08:00`，并把原值保留为 `开始时间戳(ms)`、`结束时间戳(ms)`。

`BPR录制` 页签在现有身份、业务步骤范围和状态列基础上追加：

- 可读开始、结束时间及原始时间戳
- 本地 BPR 文件和在线报告链接
- 下载状态、下载错误、概要状态、概要错误
- 固定 14 项服务端概要

指标明确不可用时 Excel 留空，不用 0 冒充采集失败，也不为每项再增加可用性列。

## 测试策略

实现采用最小 TDD 覆盖：

- 配置：完整、缺失、半配置以及秘密不外泄。
- 网络：请求体大小主路径、回退路径、不可用状态和启动步骤归属。
- 内存：正常快照、无页面、页面关闭和失败步骤。
- BPR 下载：原始链接 origin 和同源 CAS、URL 报告键与页面 BPR ID 分离、真实 download 事件、超时、登录失败、私有临时目录、原子发布及文件权限。
- HTML 解析：精简脱敏 fixture 覆盖 14 项完整、部分缺失和无概要。
- Excel：上传量、JS 堆、可读时间、原始时间戳、本地文件和服务端概要。
- HTML 报告：本地文件与合法 HTTPS 在线链接同时可用，非法在线地址既不成链也不显示原值。
- 安全回归：报告、Excel、事件和错误文本不包含 BPR 用户名或密码。

用户提供的典型 BPR 文件 `/Users/ken/temp/ydf-browser-问题反馈/BPR - YonBIP Monitoring Center-ydf19ff00e23d08544b29e.html` 只用于本地真实解析验证，不复制进仓库；仓库只保存精简脱敏 fixture。

## OpenSpec 与文档

新建 OpenSpec change `enrich-performance-and-bpr-reports`，更新以下既有能力规格：

- `performance-xlsx-report`
- `bpr-step-recording`
- `environment-config-resolution`

同步配置示例、README、BPR 能力测试说明和相关测试。DSL 没有新增字段，因此不修改 DSL schema。

## 最终真实验收

最终真实 DSL 固定为：

```text
/Users/ken/temp/ydf-browser-问题反馈/fund_counterpart_basic_maintenance.yaml
```

该文件包含一个 `create-main-child-save` 用例及“新增”“保存”两段 BPR。设计阶段已使用当前 worktree 源码完成 DSL 校验，结果为 1 个 suite、1 个 case 且校验通过；这只证明语法有效，不代表真实页面验收通过。

最终验证必须从 worktree 当前源码运行该精确文件并开启 `--performance`，报告写入仓库外的新临时目录。验收同时检查：

- 业务断言通过，而不只检查 CLI 退出码。
- 两个 BPR session 均使用独立账号完成真实下载。
- 本地 BPR 文件存在于报告目录且权限为 `0600`。
- BPR ID、在线链接、本地文件和 session 相互对应。
- `report.json`、`report.html`、`performance.xlsx` 的状态和路径一致。
- 服务端概要真实进入 `BPR录制` 页签。
- 步骤总览包含上传量和可用的 JS 堆快照。
- BPR 后处理不污染业务步骤耗时或业务用例结果。

若本机缺少真实 BPR 凭据，线上下载验收必须明确标为阻断；不得用本地样例解析或单元测试冒充真实下载成功。

交付前依次运行聚焦 pytest、典型 BPR 文件解析、OpenSpec strict 校验、OpenSpec 语言检查、全量 pytest、`git diff --check` 和上述真实 DSL。
