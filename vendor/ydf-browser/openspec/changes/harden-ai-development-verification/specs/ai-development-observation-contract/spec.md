## ADDED Requirements

### Requirement: AI 观察运行必须声明验证入口资格
系统 MUST 在 AI 观察报告中区分默认安装冻结 helper 启动与直接 CLI 启动；直接 `--ai-observe` 只表示观察执行事实，不得成为 `verified` 的合格运行。

#### Scenario: 预检声明验证入口能力
- **WHEN** helper 运行 `ydf-browser doctor --skip-config`
- **THEN** `contract_version` MUST 使用兼容 minor 版本 `1.2`
- **AND** `capabilities.available` MUST 包含 `verification_entrypoint`

#### Scenario: 默认安装 helper 启动观察运行
- **WHEN** 默认安装的冻结 helper 调用 PATH 中解析出的 `ydf-browser`
- **THEN** 报告 MUST 声明 `entrypoint=skill_helper` 和当前 helper SHA-256
- **AND** helper MUST 在运行前核对该 SHA-256、PATH runtime 以及 `.agents` 和 `.codex` 两份默认安装 skill 的目录指纹与冻结 manifest 一致

#### Scenario: 直接启动 AI 观察运行
- **WHEN** 用户或 agent 直接执行 `ydf-browser run --ai-observe`
- **THEN** 报告 MUST 声明 `entrypoint=direct_cli` 和 `verification_eligible=false`
- **AND** 机器验证结果 MUST NOT 把该运行计为合格红灯或绿灯

#### Scenario: 冻结指纹不一致
- **WHEN** helper、PATH runtime 或任一默认安装 skill 的当前指纹与 verification manifest 不一致
- **THEN** helper MUST 在启动浏览器前以 `blocked/contract_incompatible` 停止
- **AND** 不得创建可误认为真实运行证据的报告

### Requirement: 合格 AI 运行必须通过独立 cleanup DSL 收尾
helper SHALL 复用现有 DSL 和外部变量能力执行独立 cleanup DSL，并 MUST 在主运行成功、失败或外部终止后执行清理；第一次清理失败时 MUST 幂等重试一次。

#### Scenario: 主运行失败后执行清理
- **WHEN** 主观察运行产生 assertion failure、blocked 或 terminated 结果
- **THEN** helper MUST 使用同一个冻结 runtime、转发规则和外部变量执行 manifest 声明的 cleanup DSL
- **AND** 清理证据 MUST 写入主运行目录下的独立子目录并被 `external-result.json` 引用

#### Scenario: 第一次清理失败
- **WHEN** cleanup DSL 第一次运行返回失败或缺少完整报告
- **THEN** helper MUST 使用新的清理证据子目录重试一次
- **AND** 第二次仍失败时 MUST 记录 `cleanup_failed` 和最后可用报告，不得宣称验证完成

#### Scenario: 合格运行缺少清理证据
- **WHEN** 最终结果尝试把没有 helper cleanup 成功证据的运行标记为 qualified
- **THEN** 结果写入 MUST 失败
- **AND** 仅在最终 JSON 手工写入 `cleanup.success=true` MUST NOT 绕过该门禁
