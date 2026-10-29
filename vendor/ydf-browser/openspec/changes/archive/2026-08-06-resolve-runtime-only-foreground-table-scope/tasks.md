## 1. 红灯与根因

- [x] 1.1 对照 `ai-observe-7` 报告、DOM 摘要和 manifest，确认前景表格 DOM 已存在但未进入 manifest region 候选集
- [x] 1.2 增加精确 runtime fieldid 的最小回归测试，并连续两次观察 `not-found` 红灯

## 2. 共享解析修复

- [x] 2.1 在表格作用域共享入口增加 manifest 未命中后的精确 runtime fieldid 受限探测
- [x] 2.2 覆盖成功、缺失和不回退语义，运行表格作用域聚焦测试

## 3. 端到端与交付验证

- [x] 3.1 使用当前源码和真实 DSL 验证动态模板弹窗前景表格可解析，并保留结构化报告证据
- [x] 3.2 运行完整 pytest、OpenSpec strict 校验、语言检查和 `git diff --check`
