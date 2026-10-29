## MODIFIED Requirements

### Requirement: 冷启动真实业务试点必须作为完成门禁
本 change MUST 使用一个未知根因的独立 evaluator 完成真实业务 Bug 的修改前红灯和修改后连续绿色闭环；静态源码判断、合成故障、已知根因提示或直接浏览器操作均不得替代该门禁。

#### Scenario: 以指定弱模型无历史启动
- **WHEN** 启动冷启动 evaluator
- **THEN** evaluator MUST 使用 `gpt-5.6-luna` 和 `xhigh` 推理强度
- **AND** MUST 通过 `codex exec --ephemeral --disable memories --json` 禁用持久记忆后运行，并保存 `evaluator-events.jsonl` 和 `evaluator-final.md`
- **AND** 仅使用 `--ephemeral` 而未禁用 `memories` MUST NOT 视为无历史启动
- **AND** 输入 MUST 只包含原始 Bug 描述、业务仓库、转发参数、服务控制方式、用户明确提供的租户/默认组织/用户别名执行上下文和待验收 skill，不得包含根因、现成 DSL 或本次设计记录
- **AND** evaluator MUST 根据原始 Bug 自行编写真实 DSL，并在合格红灯和两次绿色验证中使用内容不变的同一 DSL

#### Scenario: 冻结验证器和 skill
- **WHEN** 试点开始
- **THEN** 系统 MUST 为同一个带新版本号的发布候选 ZIP 计算 SHA-256，并从该包分别执行 runtime 与 skill 安装器写入默认目录
- **AND** 用户目录下已安装 `ydf-browser`、`.agents/skills/gov-ydfdev-browser` 规范副本和 helper MUST 对 evaluator 只读并计算路径或内容指纹
- **AND** verification manifest MUST 使用 `agents_skill` 记录该唯一规范副本的目录指纹，并 MUST NOT 要求独立的 `codex_skill` 指纹
- **AND** 实际可执行文件路径、工具版本、契约版本和启用能力 MUST 进入私有验证证据
- **AND** 安装前 MUST 记录既有 runtime 与 skill 的路径和指纹；验证失败时 MUST 恢复既有安装，验证通过时 MUST 保留已验证候选
- **AND** 试点结束时任一验证器或 skill 指纹变化 MUST 使结果为 `invalid`
- **AND** 目录指纹 MUST 覆盖安装包内文件，但 MUST 排除缓存、报告等运行产物

#### Scenario: 保护业务仓库已有改动
- **WHEN** 业务仓库在试点开始前存在脏工作区
- **THEN** skill MUST 记录 HEAD、porcelain 状态、修改和未跟踪文件清单及 SHA-256，并在私有目录保存必要基线
- **AND** evaluator MUST NOT reset、clean 或还原用户已有改动
- **AND** 已有脏文件被意外改变 MUST 产生 `invalid/preexisting_change_modified`
- **AND** 修复确需重叠修改时 MUST 分别表达基线内容和 evaluator 新增差异

#### Scenario: 修改前必须先获得真实红灯
- **WHEN** evaluator 准备修改业务代码
- **THEN** evaluator MUST 已经通过默认目录中的冻结 skill 和安装版工具执行真实 DSL
- **AND** evaluator MUST 在首次运行前创建并冻结 `verification-manifest.json`；skill 的每次运行入口 MUST 要求该清单、核对 DSL 与 readiness 路径并记录清单 SHA-256
- **AND** evaluator MAY 在合格红灯前保持同一 DSL 路径并修订内容；每次运行 MUST 记录实际 DSL SHA-256，合格红灯后 MUST 锁定内容
- **AND** 在取得合格红灯前 MUST NOT 写入业务仓库中的任何文件；临时日志、诊断探针、埋点或计划随后回退的修改均视为违规并使试点无效
- **AND** 红灯 MUST 到达与 Bug 相关的业务断言
- **AND** API 与 UI 双层证据 MUST 围绕同一临时业务唯一标识证明修改前前置条件和修改后异常结果
- **AND** 合格运行 MUST 在同一 skill helper 运行目录内包含前置查询、业务修改和后置断言三个不同的已完成请求；诊断用直接浏览器或 API 调用不得补齐其中任一阶段

#### Scenario: 修改后必须连续获得两次绿色
- **WHEN** evaluator 完成业务代码修改并确认新服务就绪
- **THEN** evaluator MUST 使用红灯时的同一 DSL 和两组新的、互不复用的临时业务数据连续执行两次绿色验证
- **AND** 最终结果 MUST 机器校验合格红灯和两次绿色运行记录的 DSL SHA-256 完全一致
- **AND** 最终结果 MUST 机器校验红灯与两次绿色的 API/UI 业务标识各自一致且三组标识互不复用
- **AND** 最终结果 MUST 依据每个运行目录的 `external-result.json`、报告、网络索引和正文证据，校验前置查询、业务修改和后置断言请求按顺序由同一次冻结 skill 运行产生；前置查询、业务修改和绿色后置请求 MUST 携带该次业务标识，红灯的负向后置响应仅可在选定请求由同目录真实失败断言回执引用时不包含已消失的业务标识
- **AND** 每次相关保存和查询请求 MUST 实际命中预期本地转发目标
- **AND** 两次运行 MUST 分别使用新的证据目录并完成临时数据清理

#### Scenario: E2E 必须经过冻结 skill
- **WHEN** evaluator 取得红灯或绿色证据
- **THEN** 证据 MUST 由默认安装的冻结 gov-ydfdev-browser skill helper 调用 `PATH` 中已安装的 `ydf-browser` 产生
- **AND** helper、`ydf-browser` 子进程和 evaluator MUST NOT 读取或调用 ydf-browser 源码目录或解压目录
- **AND** Playwright 脚本、浏览器 MCP、人工点击或直接 API 调用 MUST NOT 替代 UI 断言
- **AND** 额外 API 调用 MAY 辅助诊断但 MUST NOT 计入门禁

#### Scenario: evaluator 不扩大到代码交付权限
- **WHEN** evaluator 修改和验证业务系统
- **THEN** evaluator MUST NOT 执行 git add、commit、push、rebase 或分支切换
- **AND** 最终结果 MUST 只引用相对业务工作区基线的本地差异，由用户决定是否提交

#### Scenario: 工具缺口使本次试点停止
- **WHEN** 冷启动 evaluator 发现冻结验证器或 skill 缺少完成试点所需能力
- **THEN** 本次试点 MUST 以 blocked 停止
- **AND** 修复工具后 MUST 从新的修改前红灯运行重新开始，不得在同一试点中边测边改验证器
