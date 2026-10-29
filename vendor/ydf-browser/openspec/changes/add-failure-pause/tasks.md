## 1. TDD 回归

- [x] 1.1 为 `--pause-on-failure` 的 CLI help、有效组合和启动前不兼容参数校验添加红灯测试
- [x] 1.2 为首个可检查失败的等待顺序、stderr 提示、`failure_pause` 记录和 Enter 后清理添加红灯测试
- [x] 1.3 为无活页面不暂停、整次运行停止和 Ctrl-C 返回 `130` 添加红灯测试
- [x] 1.4 为 `PlaywrightRuntime.has_open_page()` 的打开、关闭和异常状态添加红灯测试

## 2. 最小实现

- [x] 2.1 增加 CLI 参数及集中兼容性校验，并将有效 suite 失败策略收敛为 `stop_run`
- [x] 2.2 增加运行时活页面查询，并在执行器失败报告返回后、现有清理前实现同步 Enter 暂停
- [x] 2.3 写入 `report.timing.failure_pause`，保持提示走 stderr、最终 JSON 走 stdout，并完成 Ctrl-C 清理与 `130` 收尾

## 3. 用户文档

- [x] 3.1 更新 `CONTEXT.md`、CLI help 和运行指南，说明适用边界、命令示例、Enter/Ctrl-C 与报告语义

## 4. 自动验证

- [x] 4.1 运行聚焦 CLI/runtime/runner 测试、`git diff --check`、严格 OpenSpec 校验和语言检查
- [x] 4.2 运行完整 `./.venv/bin/python -m pytest -q` 并核对零失败

## 5. 真实页面验收

- [x] 5.1 用当前源码和临时真实 DSL 制造业务断言不符合，确认失败页面保持、后续用例未执行、Enter 后报告为失败且包含 `failure_pause`

## 6. 主动关闭自动收尾

- [x] 6.1 为关闭失败页签/浏览器自动结束等待并记录 `ended_by=browser_closed` 添加红灯测试
- [x] 6.2 以标准库最小竞速实现 Enter 与失败页面关闭中先发生者收尾，复用协议探测识别 browser 断连，并使已关闭资源清理幂等
- [x] 6.3 更新 CLI help、用户指南与报告说明
- [x] 6.4 运行聚焦/全量测试、OpenSpec 校验，并用临时真实 DSL 确认主动关闭后自动退出与完整失败报告
