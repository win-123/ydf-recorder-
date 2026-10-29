# ydf-browser AI 开发指南

本指南面向 AI 修改 YonDiF 业务系统代码后的端到端验证。被测对象是业务系统，ydf-browser 只提供可观察、可审计的验证执行事实。

## 两种使用方式

普通 DSL 编写和测试回归使用安装版命令：

```bash
ydf-browser doctor
ydf-browser validate --dsl examples/your_suite.yaml
ydf-browser run --dsl examples/your_suite.yaml --headless
```

AI 业务开发验证必须从同一个冻结发布 ZIP 安装 runtime 和 skill 到默认目录，并只使用 PATH 中的安装版命令：

```bash
./scripts/install-runtime.sh
ydf-browser install-skill
command -v ydf-browser
YDF_BROWSER_AUTO_UPDATE=0 ydf-browser doctor --skip-config
python3 "$HOME/.agents/skills/gov-ydfdev-browser/scripts/ai_verification.py" run \
  --dsl /private/case.yaml \
  --cleanup-dsl /private/cleanup.yaml \
  --readiness-file /private/readiness.json \
  --verification-manifest /private/verification-manifest.json \
  --run-dir /private/run-001 \
  --var business_id=AI-001
```

安装前记录既有 runtime 与 skill 路径和指纹；验证失败时恢复，验证通过时保留候选安装。helper 只能从默认安装后的 skill 目录启动，并只调用 PATH 中解析出的 `ydf-browser`；源码目录和解压目录不得作为运行入口。直接执行 `ydf-browser run --ai-observe` 的报告会标记 `direct_cli` 和 `verification_eligible=false`，只能作为观察事实。

AI 验证使用冻结的 runtime、skill 和 helper 指纹，因此编排命令会显式设置 `YDF_BROWSER_AUTO_UPDATE=0`，避免验证期间发生版本漂移。普通安装版运行仍可保持默认的后台更新；更新不会覆盖 skill，若 runtime 声明的最低 skill 版本不满足，`doctor` 会报告不兼容，AI 预检会以 `blocked/contract_incompatible` 阻断验证。

`doctor --skip-config` 必须返回兼容的 `contract_version` 和所需 `capabilities.available`；不兼容时停止为 `blocked/contract_incompatible`，不启动浏览器。发布 ZIP SHA-256、实际可执行文件路径和真实路径、版本、契约能力及已安装 skill/helper 指纹进入私有验证证据。

## 编写用例前的参照探索

测试 DSL 仅描述业务操作和断言。编写用例时可用 `run --ai-observe` 查看成功步骤页面摘要中的 `reference_candidates`，该采集不展开或筛选参照。

同一摘要的控件节点通过 `field_label` 关联当前字段，`required` 和 `required_sources` 给出必填状态及依据；`null` 表示未知。`constraint_attributes` 保留公开的类型、长度、范围、步长和 pattern 属性，`placeholder` 保留输入提示。这些只是当前 DOM 事实，不涵盖全部业务规则；录入前核对已知必填项，保存后仍按真实校验和字段读回判定结果。普通运行和测试 DSL 不变。

需要主动展开时，在只包含导航和打开参照的探索用例上增加 `--explore-reference '{"title":"参照标题","path":["已观察根节点"]}'`。参数只在成功用例末尾执行，探索状态和证据路径位于末步 `data.reference_exploration`，不改变原测试结果。没有参照时报告探索失败；失败用例跳过。支持 `filter`、`tree_fieldid`、`offset`、`limit`，后两者只分页当前已渲染结果；候选完整性始终未知。探索不选择、确认或保存。生成的正式用例继续使用普通 DSL，并移除探索参数。

## 显式服务就绪检查

每个转发目标必须单独声明 `target`、`url`、`timeout_seconds`、`tls_verify` 和模式：

- `http_reachable`：完成 TCP、TLS 和 HTTP 交互即为可监听，任意 HTTP 状态都可以。
- `semantic_probe`：还要校验 `expected_status`、`json_path` 和 `equals`。

不得根据转发路径、端口或地址猜测服务是前端还是后端。就绪只允许开始验证，不能证明真实业务请求命中了本地代码。样例见 `skills/gov-ydfdev-browser/references/readiness.example.json`。

## AI 观察目录

每次运行使用业务仓库外一个全新且权限为 `0700` 的目录。`--report-file` 确定以下交接位置：

- `report.json`：最终结构化报告和断言回执；
- `events.jsonl`：逐条 flush 的语义事件；
- `artifacts/network/index.jsonl`：候选业务请求生命周期和本地转发事实；
- `artifacts/errors/index.jsonl`：用例期 console/page error；
- `artifacts/cases/<case>/`：安全截图、DOM 摘要、失败证据包和表格断言快照。

AI 模式默认 step/case/run 超时为 120/900/1800 秒，只允许串行执行。skill 在 run timeout 之后保留 30 秒外部 watchdog；外部终止只依据已经 flush 的证据表达 `terminated/external_termination`。

网络正文默认单个上限 10 MiB、单用例上限 200 MiB。超限、二进制、multipart 或不能安全脱敏的正文整块跳过，不保存部分正文或正文哈希。URL、headers、JSON、表单和 XML 在持久化前脱敏。

## 从执行事实到验证结论

业务断言回执只列出最近非断言步骤之后的候选 `request_id`，工具不会自动选择相关 API。AI 必须用同一个新临时业务唯一标识核对：

1. UI 断言回执；
2. 相关 API 的完整脱敏语义正文；
3. 该请求的终态；
4. `forwarding.matched` 与 `forwarding.success`；
5. 实际本地目标 URL。

DSL 绿色但正文不可用、API/UI 标识不一致或没有真实本地转发命中时，只能写 `not_verified/evidence_unavailable`。工具不会输出 `business_bug`、`bad_data`、业务根因或修复建议。第一阶段没有通用 `api.assert` DSL。

Bug 修复门禁是：修改前同一 DSL 必须真实红灯；修改后用两组全新数据连续两次绿灯。每次主运行结束后，helper 都使用独立 cleanup DSL 和同一组 `--var` 执行清理，失败时幂等重试一次；随后复核验证器与 skill 指纹。任一门禁缺失都不能写 `verified`。

机器可读输入基线写入 `verification-manifest.json`，其中固定发布 ZIP、安装版 runtime、`agents_skill` 规范副本和 helper 指纹；最终结论原子写入 `verification-result.json`。schema、样例、完整编排命令和证据筛选规则位于默认安装的 gov-ydfdev-browser skill `references/`。
