## Context

见 `proposal.md` 的动机和三份 delta spec 的行为契约。当前 `--performance` 已采集步骤耗时、网络下载量和 BPR 在线链接，但缺少上传量、步骤结束时页面 JS 堆以及可离线分析的 BPR 原始文件和服务端概要。

本设计遵循 `CONTEXT.md` 的领域边界，并直接采用 ADR 0013 的独立 BPR 凭据和 ADR 0014 的原文归档决策。BPR 后处理属于报告增强，不得污染业务 DSL 执行计时、业务用例结果或 CLI 二值退出语义。

## Goals / Non-Goals

**Goals:**

- 在现有网络请求归因模型中补充上传字节数和不可用原因，不保存请求体内容。
- 在动作耗时结束后补充顶层页面 JS 堆单次快照。
- 在业务 DSL 全部完成后统一下载、保存并解析 BPR 报告，再生成性能工作簿和最终报告。
- 让 JSON、HTML 和 Excel 对 BPR session 的在线链接、本地文件、状态、时间和固定概要保持一致。
- 将凭据、原始 BPR 内容和错误文本的传播边界固定为可测试的安全契约。

**Non-Goals:**

- 不新增 DSL 字段，不改变业务用例成功语义、运行 `success` 或 CLI 退出码。
- 不改变轻量执行计时和 Web Vitals 语义，不采集页面内存峰值、步骤增量、iframe 总量或浏览器 RSS。
- 不支持可插拔认证、动态概要列、BPR 内部文件接口、页面内存峰值采样或严格下载模式。
- 不保证 BPR 原始文件的全部外部脚本可以离线运行，也不将其视为已脱敏文件。

## Decisions

### 1. 在运行结束后统一后处理 BPR

业务 DSL 全部执行完成后、生成 `performance.xlsx` 前，由 `ydf_browser/cli.py` 调用一次 `ydf_browser/bpr_report.py` 后处理入口。该小型模块遍历 sessions、编排下载和解析并回填结果；`performance_xlsx.py` 和 `report_html.py` 只消费已回填数据。

这样可避免在每个 `bpr.stop` 中重复登录、等待和下载，也不会把 BPR 报告生成时间算入业务步骤耗时。一次运行只建立一个独立登录会话和浏览器上下文，多个 session 顺序处理。

### 2. BPR 下载只使用独立凭据和真实浏览器下载

按 ADR 0013，在环境配置中读取 `bpr.username/password`。两项均缺失时记录 `not_configured`，只配置一项时在浏览器启动前失败，完整配置时也不回退到业务登录态。

下载复用现有 YonDiF/YHT 登录器和 Playwright 下载能力，但认证目标只能来自可信 `bpr.stop` 结果中的 `report_url` origin。后处理先要求 URL 为无 userinfo 的绝对 HTTPS URL，再用同一 HTTP session 打开首个原始 `report_url` 并跟随重定向；只有最终登录页仍是该 HTTPS origin 时，才向实际 CAS 登录 URL 提交独立凭据。业务登录未提供入口 URL 时仍使用既有 `/login_light` 链路。一次运行只建立一个隔离登录会话和浏览器上下文，其它报告 origin 或跨 origin 登录页安全失败且不得接触凭据。配置只保留 `bpr.username/password`，不增加或回退任何 BPR 地址字段。

每个 session 从开始打开原始 `report_url` 时用单调时钟建立一个固定 60 秒 deadline；页面打开、页面内 BPR ID 校验、下载按钮等待和 download 事件完成都只消费同一个剩余预算，任何阶段不得重置或延长期限。URL 的 `pk` 是报告记录键，不要求等于 session BPR ID；导航后仍必须确认 `window.pageData?.bprBaseInfo?.bprId` 与 session 一致。不调用未公开文件接口，也不新增认证或超时配置分支。

后处理先检查每个 session 的 `report_url`，再判断凭据。既有失败 session 没有链接时始终记录 `download_status=failed`、安全错误摘要和 `summary_status=not_attempted`，即使凭据未配置也不标记为 `not_configured`，不导航空 URL，也不改变业务结果。`not_configured` 只适用于有 `report_url` 但缺少独立 BPR 凭据的 session。

### 3. 原始 BPR 文件按下载原文保存

按 ADR 0014，下载文件保存到 `artifacts/<suite>/<case>/bpr/<index>-<bpr_id>.html` 并设置 `0600`。JSON 和 Excel 保存绝对路径，HTML 报告使用相对链接，以便整体移动报告目录。

原始文件不改写、不进入 `diagnostic_files` 或版本控制；原始 HTML 全文、源码和固定 14 项概要之外的任意片段不得进入事件、错误文本、控制台、工作簿或 JSON/HTML 报告。按固定字段映射提取的 14 项用户可见概要允许作为结构化 `server_summary` 和工作簿列输出，不属于原文泄漏。解析失败只影响概要状态，不删除文件或覆盖成功下载状态。

### 4. 使用标准库解析固定服务端概要

`bpr_report.py` 使用 `HTMLParser` 流式读取 UTF-8 HTML，定位 `#summary-posi`，从首行 `th/td[data-field]` 提取规格固定的 14 项用户可见文本。完整为 `parsed`，部分为 `partial`，没有概要或解析异常为 `failed`；未知字段忽略，缺失字段留空。

固定列保持工作簿结构稳定，同时不执行内嵌 JavaScript、不解析 `pageData`、不引入 `bs4` 或 `lxml`，也不依赖未公开 BPR 接口。

### 5. 上传量沿用请求启动步骤归因

每个请求完成或失败时依次读取 Playwright request size、已有请求体字节长度和 `Content-Length`；浏览器关闭使 response size 读取被取消时回退 `Content-Length`，不让回调异常进入控制台。`GET/HEAD` 无其它证据时记为 0，其余无法确定时保存不可用原因。请求仍归属于启动步骤，避免异步完成时误计入后续步骤。

底层只保存字节整数或不可用原因，不保存请求体内容。请求体不得因上传量采集进入事件、错误文本、控制台、工作簿或 JSON/HTML 报告。只要步骤中一个相关请求无法测量，步骤上传量就不可用，Excel `上传KB` 留空；KB 换算只发生在导出层。

### 6. JS 堆在动作计时结束后单次读取

性能模式在每个实际执行步骤结束后读取顶层页面 `performance.memory.usedJSHeapSize`，覆盖成功、失败和 BPR 控制步骤。无页面、页面关闭或不支持时记录不可用原因，不抛出业务异常。

读取发生在动作耗时停止计时之后。底层保留字节数，Excel 转为 MB 并保留两位小数，明确表达这是步骤结束时快照而不是峰值或增量。

### 7. 报告层只展示同一份 session 数据

BPR session 保留 `report_url`，新增 `report_file`、下载和概要状态、相应安全错误摘要及 `server_summary`。JSON 保留 epoch 毫秒，`BPR录制` sheet 同时输出本地时区可读时间和原始毫秒值，并追加本地/在线入口、状态和固定 14 项概要。

后处理失败不回写业务执行状态。HTML 报告同时提供本地相对链接和在线链接；工作簿明确不可用的上传、内存或概要值留空，不使用 0 冒充失败。

## Risks / Trade-offs

- [BPR 页面生成时间或结构漂移] → 从打开报告到 download 事件完成共用单调时钟 60 秒 deadline；失败记录安全摘要并保留业务结果与在线链接。
- [不可信报告地址导致凭据外送] → 登录前只接受 `bpr.stop` 返回的无 userinfo 绝对 HTTPS URL，并把一次运行限制在一个报告 origin；非法或跨 origin session 安全失败且不提交凭据。
- [原始 BPR 文件含用户标识或业务诊断数据] → 权限固定为 `0600`，禁止输出正文、进入版本控制或声称已脱敏。
- [部分请求无法取得请求体大小] → 整个步骤上传量标记不可用并在 Excel 留空，避免不完整总数被误解为真实上传量。
- [部分浏览器不支持 `performance.memory`] → 把 JS 堆作为可选快照，记录不可用原因而不影响业务执行。
- [固定概要字段随 BPR 页面演进] → 未知字段忽略、缺失字段留空并标记 `partial`，避免动态列破坏工作簿契约。
- [串行下载延长运行后处理时间] → 下载发生在业务步骤计时之外；当前规模优先使用一个会话减少认证开销，不引入并发状态管理。

## Migration Plan

1. 先增加配置模型及成对校验，保持两项均缺失时的业务运行兼容性。
2. 分别补充上传量、JS 堆、BPR 解析与下载数据契约，并以聚焦测试锁定安全和失败语义。
3. 在运行结果完成后、工作簿导出前接入一次 BPR 后处理，再更新 Excel、HTML、配置示例和文档。
4. 使用精确真实 DSL 验证两个 BPR session 的独立登录、真实下载、`0600` 权限、概要和跨产物一致性；缺少真实凭据时保留验收阻断状态。
5. 回滚时移除后处理调用和新增展示列即可；既有 DSL、在线 BPR 链接和业务结果语义保持兼容。
