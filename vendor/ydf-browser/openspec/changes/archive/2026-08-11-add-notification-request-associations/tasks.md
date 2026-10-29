## 1. 契约与文档

- [x] 1.1 创建 `proposal.md`、delta spec 和 `design.md`，固定错误提示请求关联的契约边界。
- [x] 1.2 更新 `CONTEXT.md`、ADR 0005、ADR 0008 和两份 `gov-ydfdev-browser` skill，沉淀领域语言和 agent 消费规则。

## 2. 测试

- [x] 2.1 增加失败测试：`code === 999` 且 `message` 精确匹配唯一 error notification 时，失败证据包输出 `confirmed` 关联和请求执行来源。
- [x] 2.2 增加失败测试：无唯一确定性匹配时输出 `unresolved` 候选，不产生“最可能请求”。
- [x] 2.3 增加兼容测试：HTTP 200 业务错误进入 `notification_request_associations` 时，不改变 `failed_requests` 既有语义。

## 3. 实现

- [x] 3.1 在失败证据包生成路径复用既有网络索引和正文路径，构造 `notification_request_associations`。
- [x] 3.2 实现 YonDiF `code === 999` + `message` 精确匹配规则，并保留正文不可用原因。
- [x] 3.3 只在未处理 error notification 造成非通过结果时写入该字段，不新增 CLI 参数，不影响普通回归。
- [x] 3.4 如契约能力或版本需要声明，补齐 doctor/report 的兼容字段。

## 4. 验证

- [x] 4.1 运行聚焦 pytest 覆盖新增行为。
- [x] 4.2 运行 `openspec validate add-notification-request-associations --strict` 和 `./scripts/check_openspec_language.py --change add-notification-request-associations`。
- [x] 4.3 运行 `git diff --check`；如共享 runtime/executor 改动较大，再运行完整 `./.venv/bin/python -m pytest`。
