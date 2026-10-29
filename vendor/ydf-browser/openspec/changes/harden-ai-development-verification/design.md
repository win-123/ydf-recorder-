## Context

参见 [proposal.md](./proposal.md) 的 `Why`。当前运行时已经有页面错误游标、统一错误提示后置判定、AI 观察信封、冻结 manifest、独立证据目录和更新状态文件；缺陷来自这些现有入口之间没有闭合，而不是缺少新的页面访问能力。

## Goals / Non-Goals

**Goals:**

- 把已采集的页面和提示错误带入可见步骤结论。
- 让机器门禁能够证明真实运行来自冻结 helper，并在任意主运行终态后清理临时数据。
- 让更新失败能定位到一次尝试和一个安装阶段。

**Non-Goals:**

- 不根据 JavaScript 错误文本猜测特定组件根因。
- 不新增 DSL `finally`、通用 API 断言或业务数据直读接口。
- 不让更新失败改变 `doctor` 和原业务命令的非阻断语义。

## Decisions

### 1. 保留错误事实，复用既有失败语义

`open_menu` 继续遵守“孤立 page error 不误杀已就绪工作面”的主规格，只把已去重错误加入成功步骤数据。`query.search` 加入现有点击动作错误提示集合，从而自动获得“下一步是 `notification.assert` 时允许负向断言”的成熟语义，不新增查询专用判断。

### 2. 用现有冻结指纹作为 helper 入口门禁

helper 在启动浏览器前计算 PATH runtime 文件、当前 helper 文件和 `.agents`、`.codex` 两份默认 skill 目录的 SHA-256，并与 verification manifest 比较。helper 通过进程环境把自己的 SHA-256传给 runtime；报告只把它作为可审计入口事实，最终 writer 仍以 manifest、helper 外部结果和报告三者一致为准。

不增加签名服务或秘密 token：该门禁防止普通 agent 无意绕过流程，不承担抵抗本机恶意进程伪造证据的安全边界。

### 3. cleanup 使用独立 DSL，不扩展 DSL 语言

helper 的 `run` 增加可选 cleanup DSL 和可重复外部变量。主进程结束后在 `cleanup/attempt-1` 运行清理；失败时只再运行 `attempt-2`。每次清理继续调用同一个 PATH runtime、使用 AI 观察和独立报告目录，因此失败可诊断且不会被主运行 stop policy 跳过。

最终 writer 检查 qualified 运行的 `external-result.json` 中 helper 入口和 cleanup 成功事实，避免手工把聚合 `cleanup.success` 改成 true 绕过门禁。

### 4. 更新器只增加轻量阶段状态

每次越过冷却和锁后生成 UUID `attempt_id`。更新器在清单、下载校验、解压、虚拟环境、wheel、Playwright、健康检查、切换和清理阶段更新当前内存阶段；失败状态写入该阶段。公共子进程包装器改为捕获 stderr 并抛出受限摘要，成功路径和 current 切换顺序保持不变。

## Risks / Trade-offs

- [直接 CLI 仍可伪造 helper 环境变量] → 最终 writer 同时核对冻结 manifest、helper 外部结果和报告；本地恶意伪造不在此工具的安全边界。
- [cleanup DSL 本身写错会留下数据] → 自动重试一次并明确 `cleanup_failed`，不使用高风险通用数据库清理兜底。
- [成功菜单包含页面错误可能增加报告体积] → 只复用本轮已有去重列表，不新增采集。
- [stderr 可能包含环境路径] → 仅保存 2000 字符尾部，不保存 stdout 或完整安装输出。

## Migration Plan

1. 先补聚焦失败测试，再修改共享入口。
2. 更新 skill 参考命令和安装包内容，旧的普通 DSL 运行不受影响。
3. 运行聚焦测试、完整 pytest、OpenSpec 严格校验和至少一个现有真实 DSL；真实业务试点需要已知 cleanup DSL 和临时标识时再执行，不以手工 SQL 替代。
