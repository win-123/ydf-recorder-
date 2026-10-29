## Why

`ydf-browser` 已能支持测试人员执行常规业务回归，但 AI agent 在修改被测业务系统后仍缺少稳定、机器可读的运行阶段、失败分类、完整业务 API 报文和本地转发命中证据，难以独立完成真实端到端复现、诊断和修复验证。第一阶段需要把这些黑盒过程转化为安全、可审计的观察契约，并用一个真实业务 Bug 的修改前红灯和修改后连续绿灯证明闭环成立。

## What Changes

- 新增显式 `ydf-browser run --ai-observe` 模式，在保持普通回归默认行为和现有二值退出码兼容的前提下，提供版本化观察信封、能力声明、结构化结果分类、语义阶段事件和受控超时。
- 为 AI 模式生成独立运行证据目录，保存脱敏后的同源业务 API 请求、响应与 headers、请求转发执行来源、用例错误索引、安全页面证据、表格断言快照和成功业务断言回执；所有高成本证据均采用容量保护和可恢复的流式或原子写入。
- 更新 gov-ydfdev-browser skill，使其执行契约兼容性预检、显式服务就绪检查、安装版 CLI 调用、证据筛选和机器可读验证结论，并区分执行成功与被测业务系统变更已验证。
- 以“单位资金往来对象编辑后列表不可查询”的真实业务 Bug 作为冷启动试点：冻结验证器与 skill，由无历史上下文的 `gpt-5.6-luna` evaluator 在修改业务代码前获得真实红灯，修改后使用两组新临时数据连续获得两次绿灯并完成清理。
- 同步 CLI、AI 开发指南、skill reference、示例和契约测试；不新增通用 `api.assert`，也不把业务根因判断固化到 `ydf-browser`。

## Capabilities

### New Capabilities

- `ai-development-observation-contract`: 定义 AI 辅助业务开发场景中的观察模式、结果与事件契约、安全网络和页面证据、受控超时、业务断言回执、skill 验证结论及真实冷启动验收门禁。

### Modified Capabilities

无。现有 DSL 动作、普通报告、请求转发和表格断言的既有语义保持兼容，新增行为由统一 AI 开发观察规格约束。

## Impact

- 主要影响 `ydf_browser/cli.py`、`runner.py`、`executor.py`、`runtime.py`、`request_forwarding.py` 及报告和诊断文件写入路径。
- 影响发布候选 ZIP、默认安装目录下 gov-ydfdev-browser skill 的入口和 references，并需要保持安装版 runtime、`.agents` 与 `.codex` 副本来自同一个冻结发行包。
- 新增 AI 模式 CLI 参数、观察契约字段和诊断 artifacts；普通测试人员回归不默认采集完整业务报文，也不继承 AI 模式超时或串行限制。
- 需要聚焦单元测试、完整 pytest、发布包审计、默认目录安装证明、真实 DSL 红灯与两次绿灯证据，以及 OpenSpec 结构和语言门禁；不引入新的第三方运行时依赖。
