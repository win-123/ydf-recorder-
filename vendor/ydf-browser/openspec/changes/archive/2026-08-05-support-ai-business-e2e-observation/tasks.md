## 1. 契约入口与兼容基线

- [x] 1.1 为 `doctor --skip-config` 的 `tool_version`、`contract_version`、`capabilities.available` 和兼容性演进规则补充失败测试，再实现最小能力声明。
- [x] 1.2 为 `run --ai-observe`、三个超时参数和两个网络容量参数补充 CLI 解析与非法组合测试，再实现正数、层级和 AI 模式限定校验。
- [x] 1.3 为 AI 模式拒绝 `concurrency > 1`、fixture/普通模式兼容及旧二值退出码补充测试，再实现浏览器启动前的 `blocked/contract_incompatible`。
- [x] 1.4 为 DSL 校验失败仍覆盖本轮 `report.json`、`events.jsonl` 且不启动浏览器补充测试，再把首个 `run_started` 事件提前到现有 DSL 加载边界。

## 2. 观察会话与可靠持久化

- [x] 2.1 为统一信封、单调 sequence、作用域字段、能力与实际配置补充契约测试，再在 `ydf_browser/observation.py` 实现一个具体观察会话。
- [x] 2.2 为 JSONL 逐条 flush、同目录临时文件原子替换、索引只引用已完成文件补充异常恢复测试，再扩展现有 `_EventLogger` 和 JSON 写入路径。
- [x] 2.3 为每次运行独立 `report.json`、`events.jsonl`、`artifacts/` 路径和旧目录不覆盖行为补充测试，再复用现有 `--report-file` 路径派生逻辑。
- [x] 2.4 为 `StepResult.success/message/data`、现有报告消费者和普通模式输出补充回归测试，再只在 AI 模式旁挂 observation 和 run 级契约元数据。

## 3. 语义事件、监督执行与超时

- [x] 3.1 为 run、suite、case、step 和 phase 的开始、成功、失败事件补充顺序测试，再从现有 CLI、runner 和 `WorkflowExecutor.run` 共同边界发送事件。
- [x] 3.2 为静默 5 秒后重复 heartbeat、普通事件重置计时及 heartbeat 不访问 DOM 补充时钟测试，再由父进程实现低噪声心跳。
- [x] 3.3 为 AI 串行工作进程、可序列化消息和普通模式原执行路径补充测试，再使用标准库进程边界运行现有串行 runner。
- [x] 3.4 为 step/case/run 首个到期者的 `terminated/timeout`、`operation_reason`、停止后续用例和协作关闭补充测试，再实现父进程截止时间监督。
- [x] 3.5 为工作进程卡死、收尾窗口耗尽、已 flush 证据保留和最终报告尽力合成补充进程测试，再实现终止兜底；不得在 watchdog 线程操作 Playwright 对象。

## 4. 结果分类与业务断言回执

- [x] 4.1 为 `passed`、`assertion_failed`、`blocked`、`terminated` 和公共 reason code 映射补充表驱动测试，再在现有 case report 汇总边界统一分类。
- [x] 4.2 为 `suite.on_case_failure` 在 `assertion_failed` 和 `blocked` 下的 continue/stop_suite/stop_run 行为补充测试，并保持当前失败用例不再执行后续步骤。
- [x] 4.3 为六类现有业务断言和 `import.upload target.assert` 排除规则补充测试，再复用 `_is_business_assertion_step` 生成 expected/actual、目标与作用域回执。
- [x] 4.4 为最近非断言步骤到当前断言的候选请求范围、连续断言共用起点和无自动相关性排序补充测试，再记录 request sequence 边界。
- [x] 4.5 为 DSL 绿色但 API 正文或本地转发命中证据不足的 skill 判定补充样例，确保工具只报告执行事实、不输出业务根因或 `business_bug`。

## 5. 安全业务网络证据

- [x] 5.1 为原始同源 URL、xhr/fetch、认证/静态/第三方/二进制/multipart 排除和转发后资格不变补充测试，再接入 `PlaywrightRuntime` 现有 request 生命周期钩子。
- [x] 5.2 为稳定 `request_id`、只追加 started/completed/failed/incomplete、跨步骤上下文和单调 sequence 补充测试，再实现 `artifacts/network/index.jsonl`。
- [x] 5.3 为浏览器原始 URL、实际 URL、命中规则、转发结果和响应状态来自同一请求补充测试，再把 `request_forwarding.py` 的真实匹配事实关联到 request lifecycle。
- [x] 5.4 为大小写和分隔符归一化、精确敏感字段、URL、headers、JSON、表单和 XML 脱敏补充安全测试，再使用标准库实现统一分类器与 `redacted_semantic` 表示。
- [x] 5.5 为不安全 `text/*`、声明与内容矛盾、正文读取失败及正文不写哈希补充测试，再实现稳定 `capture_unavailable_reason`。
- [x] 5.6 为单正文 10 MiB、单用例 200 MiB 默认值、CLI 覆盖、整块跳过且业务流程继续补充边界测试，再实现用例级容量计数。

## 6. 页面错误与失败证据包

- [x] 6.1 为整个用例期间的 console error/page error、步骤关联、凭据脱敏和无法可靠脱敏时丢弃文本补充测试，再扩展现有 runtime 缓冲与用例索引。
- [x] 6.2 为首个非通过用例只保存一张视口截图、敏感控件 mask 和任一可见 frame 遮罩失败即跳过补充测试，再实现安全截图采集。
- [x] 6.3 为有界 DOM 语义摘要排除 script/style/隐藏值并保留普通可见业务数据补充测试，再实现失败点一次性采集。
- [x] 6.4 为统一失败证据包的页面、前景层、manifest、提示、绑定候选、相邻错误和失败请求引用补充测试，再从 executor 失败出口集中触发。
- [x] 6.5 为表格断言保存当前渲染有效业务行、1 MiB 退化规则、前 10 行样本和不跨页补充测试，再复用表格作用域与断言已解析事实。

## 7. Skill 编排与机器可读结论

- [x] 7.1 更新 `.agents/skills/gov-ydfdev-browser` 事实源，使 AI 开发验证先运行 doctor 契约预检，再显式调用当前源码版 `run --ai-observe --report-file`；同步 `.codex` 副本并校验内容一致。
- [x] 7.2 为 readiness 清单补充 `http_reachable` 和 `semantic_probe` 样例与检查，要求显式 target、URL、超时和 TLS 策略，禁止从转发路径推断服务类型。
- [x] 7.3 为超出 run timeout 30 秒的外部 watchdog 补充终止流程，并只依据已 flush 证据输出 `terminated/external_termination`。
- [x] 7.4 实现 skill 的候选请求筛选、API/UI 唯一标识核对和本地转发命中检查，明确“执行成功”不能替代“业务变更已验证”。
- [x] 7.5 为 `verification-manifest.json` 和原子写入的 `verification-result.json` 补充 schema/样例，覆盖 `verified`、`not_verified`、`invalid`、清理失败和证据引用。
- [x] 7.6 更新 AI 开发指南、CLI 文档和最小 DSL/运行示例，说明安全边界、容量、证据目录、原因码及第一阶段无 `api.assert`。
- [x] 7.7 要求 skill helper 的每次观察运行都传入首次运行前已创建的 `verification-manifest.json`，核对 DSL/readiness 路径并记录清单 SHA-256，防止事后补写清单。

## 8. 工程验证与冻结

- [x] 8.1 运行观察、CLI、runner、executor、runtime、request forwarding 和 skill 的聚焦测试，并修复所有失败。
- [x] 8.2 运行完整 `./.venv/bin/python -m pytest`、`git diff --check`、OpenSpec 严格校验和语言检查，确认普通回归与新增 AI 模式均通过。
- [x] 8.3 使用非业务 fixture 验证 DSL 无效、受控超时、网络脱敏、容量超限和进程终止后的 artifact 可恢复性。
- [x] 8.4 使用至少一个真实 YonDiF DSL 验证 AI 模式的语义事件、完整业务 API 证据、转发命中、断言回执和普通模式兼容。
- [x] 8.5 固定当前源码版 ydf-browser 与两份 gov-ydfdev-browser skill，记录版本、整个目录 SHA-256 指纹和只读状态；后续试点期间不得修改验证器。

## 9. 冷启动真实业务 Bug 门禁

- [x] 9.1 在代码仓库外创建权限 `0700` 的私有试点目录，记录业务仓库 HEAD、porcelain、已有修改/未跟踪文件清单与 SHA-256 基线，不 reset、clean 或覆盖用户改动。
- [x] 9.2 为“单位资金往来对象编辑后列表不可查询”只准备显式 readiness 输入，其中后端使用用户提供的 `/_yms/ready` 语义探针，其他目标不推断服务类型；真实 DSL 必须由 evaluator 根据 Bug 自行编写，并在红灯和两次绿灯中保持同一文件内容。
- [x] 9.3 通过 `codex exec --ephemeral --disable memories --json` 启动无历史 `gpt-5.6-luna`、`xhigh` evaluator，只传原始 Bug 描述、业务仓库、转发参数、服务控制方式、用户明确提供的租户/默认组织/用户别名执行上下文和冻结 skill，并保存 evaluator 事件与最终说明。
- [x] 9.4 审核 evaluator 在写入业务仓库任何文件前已通过冻结 skill 获得真实红灯，临时日志、诊断探针或计划回退的修改也不得例外；UI 断言和完整 API 证据须围绕同一新临时业务唯一标识并实际命中本地转发。
- [x] 9.5 审核 evaluator 修改后使用同一 DSL、两组全新数据连续获得两次绿灯，每次均有独立证据目录、API/UI 一致标识和相关保存/查询转发命中。
- [x] 9.6 审核全部临时数据完成清理、业务仓库已有脏文件未被意外改变、evaluator 未执行 git add/commit/push/rebase/切分支，且修复只表现为本地差异。
- [x] 9.7 复核冻结验证器与 skill 指纹；只有红灯、两次绿灯、清理和指纹全部通过时才写 `status: verified`，任一工具缺口必须修复后从新的红灯试点重跑。

## 10. 安装版发布候选验收

- [x] 10.1 先用失败测试证明 helper 仍依赖源码根目录，再把 doctor 与观察运行的唯一入口改为 `PATH` 中已安装的 `ydf-browser`，并记录解析后的可执行路径、版本和契约能力。
- [x] 10.2 更新 skill、AI 验证指南、机器清单和领域术语，使同一个发布候选 ZIP、默认目录 runtime/skill 安装、安装前指纹及失败恢复成为冻结合同。
- [x] 10.3 递增发布版本，构建并审计候选 ZIP；记录既有默认安装后，从同一个包执行 runtime 与 skill 安装器，并证明已安装 helper 只调用已安装 CLI。
- [x] 10.4 使用默认安装版重新执行完整冷启动试点，取得同一 DSL 的一组合格红灯和两组新数据连续绿灯，复核安装物指纹，并运行完整 pytest、发布包、OpenSpec、语言和 diff 门禁；开发环境临时数据按用户显式豁免保留，机器结果如实记录为 `not_verified/cleanup_waived_by_user`。
