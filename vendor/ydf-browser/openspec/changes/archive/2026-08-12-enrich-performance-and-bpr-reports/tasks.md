## 1. 规格基线

- [x] 1.1 建立 `proposal.md` 和 `design.md`，固定上传量、JS 堆、独立 BPR 凭据、真实下载、原文归档、服务端概要和可读时间边界
- [x] 1.2 为 `performance-xlsx-report`、`bpr-step-recording`、`environment-config-resolution` 建立 delta spec，不新增 capability
- [x] 1.3 运行 `openspec validate enrich-performance-and-bpr-reports --strict` 和 `./scripts/check_openspec_language.py --change enrich-performance-and-bpr-reports`

## 2. 配置

- [x] 2.1 先补充配置测试，覆盖 BPR 凭据完整、均缺失、只配置一项及秘密不外泄
- [x] 2.2 在环境配置模型中解析可选 `bpr.username/password`，并在浏览器启动前执行成对校验
- [x] 2.3 更新提交的配置示例，只使用 BPR 凭据占位值

## 3. 上传量

- [x] 3.1 先编写并运行网络采集红灯测试，覆盖 Playwright size、已有请求体、`Content-Length`、`GET/HEAD`、浏览器关闭时的 `CancelledError` 回退、不可用路径及请求体不进入事件、错误、控制台、工作簿和报告
- [x] 3.2 在请求完成或失败时只保存请求体字节数或不可用原因，并沿用请求启动步骤归因
- [x] 3.3 聚合步骤上传量；任一相关请求不可测时将步骤标记为不可用

## 4. 内存

- [x] 4.1 先补充 JS 堆快照测试，覆盖正常读取、无页面、页面关闭、浏览器不支持和失败步骤
- [x] 4.2 在每个实际执行步骤动作计时结束后采集顶层页面 `performance.memory.usedJSHeapSize`
- [x] 4.3 将 JS 堆不可用作为非业务失败状态，并覆盖 `bpr.start`、`bpr.stop` 控制步骤

## 5. BPR 解析

- [x] 5.1 创建精简脱敏 HTML fixture，并先补充固定 14 项完整、部分缺失和无概要测试
- [x] 5.2 新增 `ydf_browser/bpr_report.py`，使用标准库 `HTMLParser` 提取 `#summary-posi` 首行用户可见文本
- [x] 5.3 实现 `parsed`、`partial`、`failed` 概要状态，忽略未知字段并让缺失值留空
- [x] 5.4 使用用户提供的典型 BPR 文件执行本地真实解析验证，不把该文件复制进仓库

## 6. BPR 下载与后处理

- [x] 6.1 先编写并运行 BPR 下载红灯测试，覆盖独立登录、`report_url` 唯一地址来源、实际同源 CAS 登录页、跨源跳转在提交凭据前拒绝、绝对 HTTPS/无 userinfo、单一报告 origin、URL `pk` 不等于 session ID、页面 session ID 校验、真实 download 事件、登录失败和 `0600` 权限；并断言从打开报告到 download 事件完成共用单调时钟 deadline 且总预算不超过 60 秒
- [x] 6.2 从首个合格 `report_url` 提取登录 origin，以同一 HTTP session 打开原始链接并向实际同源 CAS 登录页提交凭据，在一个隔离浏览器上下文中登录一次并顺序处理同 origin sessions；非法、跨 origin session 或跨源登录跳转安全失败且不提交凭据
- [x] 6.3 将原始 HTML 保存到 `artifacts/<suite>/<case>/bpr/<index>-<bpr_id>.html`，保持原文且不进入 `diagnostic_files`
- [x] 6.4 回填 `report_file`、下载/概要状态、安全错误摘要和 `server_summary`，保证后处理失败不改变业务结果
- [x] 6.5 在业务 DSL 完成后、性能工作簿生成前调用一次 BPR 后处理入口

## 7. 报告导出

- [x] 7.1 先编写并运行性能工作簿红灯测试，覆盖 `上传KB`、`JS堆已用(MB)`、可读时间、原始时间戳、本地文件和固定 14 项概要
- [x] 7.2 先编写并运行 JSON/HTML 红灯测试，覆盖本地相对链接、在线链接、session 状态及无 `report_url` 的失败 session
- [x] 7.3 先编写并运行安全红灯测试，证明请求体、原始 BPR HTML 全文/源码/固定概要之外的片段及 BPR 用户名、密码不进入事件、错误文本、控制台、性能工作簿、`report.json` 或 `report.html`，同时证明固定 14 项映射概要允许作为结构化输出
- [x] 7.4 更新步骤总览，以 `上传KB | 下载KB | JS堆已用(MB) | 最慢请求` 顺序导出并让不可用值留空
- [x] 7.5 更新 `BPR录制` sheet，输出本地时区可读时间、epoch 毫秒、路径、状态、错误和固定服务端概要
- [x] 7.6 更新 JSON 与 HTML 报告，使本地 BPR 相对链接、在线链接及 session 状态一致
- [x] 7.7 实现统一输出约束，禁止请求体、原始 BPR HTML 全文/源码/固定概要之外的片段和 BPR 凭据进入事件、错误、控制台、工作簿及 JSON/HTML 报告，允许固定 14 项映射概要作为结构化输出，并运行 7.3 的安全测试转绿

## 8. 文档和静态验证

- [x] 8.1 更新 README、配置说明和 BPR 能力测试说明，明确独立凭据、敏感原文和失败语义
- [x] 8.2 运行相关聚焦 pytest、OpenSpec strict 校验、OpenSpec 语言检查和 `git diff --check`
- [x] 8.3 运行完整 `./.venv/bin/python -m pytest`

## 9. 真实验收

- [x] 9.1 使用 `mktemp -d /tmp/ydf-browser-bpr-acceptance.XXXXXX` 创建仓库外新私有目录，再从当前 worktree 源码校验并运行 `/Users/ken/temp/ydf-browser-问题反馈/fund_counterpart_basic_maintenance.yaml --performance`，将报告输出到该目录
- [x] 9.2 确认业务断言通过，且“新增”“保存”两个 BPR session 均由独立账号真实下载到对应报告目录并具有 `0600` 权限
- [x] 9.3 核对 BPR ID、在线链接、本地文件、服务端概要及 `report.json`、`report.html`、`performance.xlsx` 状态和路径一致
- [x] 9.4 核对步骤总览包含上传量和可用 JS 堆快照，且 BPR 后处理未污染业务步骤耗时或业务用例结果
- [x] 9.5 若缺少真实 BPR 凭据，将线上下载验收明确保留为阻断，不用样例解析或单元测试替代；本次已配置完整凭据，未触发阻断
