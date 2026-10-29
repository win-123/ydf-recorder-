## Context

`ConfigLoader` 目前会先选择一个 `env.yaml`，再自动读取同目录的 `env.local.yaml` 做深度合并。真实诊断结果显示，未传 `--config` 时 `default_config_path()` 优先返回 `/Users/ken/.ydf-browser/config/env.yaml`，随后合并 `/Users/ken/.ydf-browser/config/env.local.yaml`，最终 `base_url` 是 `https://tv5-ydf.yonyougov.top`。

同一时间，当前仓库的 `config/env.local.yaml` 已配置 `base_url: https://t9i-ydf.yonyougov.top`，且使用 `--config config/env.yaml` 执行 `doctor` 时最终 `base_url` 确认为 t9i。`PlaywrightRuntime.open_menu()` 只使用 `self.config.base_url` 生成 `/#/service/<serviceCode>`，因此打开 tv5 菜单的根因在配置发现层，而不是菜单 route 拼接层。

本项目同时支持两类使用者：安装版用户主要编辑 `~/.ydf-browser/config/env.yaml`，源码维护者和能力验证文档则会把真实账号与目标环境放在仓库 `config/env.local.yaml`。修复需要兼顾这两种入口。

## Goals / Non-Goals

**Goals:**

- 未显式指定配置时，只要当前工作目录存在 `config/env.local.yaml`，默认运行就使用当前工作目录 `config/env.yaml` 与该 local override，确保本地配置的 `base_url` 参与 API 登录、菜单查询和浏览器打开。
- 保持 `--config` 与 `YDF_BROWSER_CONFIG` 的最高优先级，不对显式配置做二次猜测。
- 在 `doctor` 输出中暴露实际选择的主配置、本地 override 路径、local 是否存在、最终 `base_url`，降低后续环境误判成本。
- 用单测覆盖默认配置选择，并用用户提供的真实 DSL 作为人工/真实环境验证命令。

**Non-Goals:**

- 不改变 `open_menu` 的 `/#/service/<serviceCode>` 打开策略。
- 不改变 DSL 中 `suite.tenant`、`suite.default_org`、`cases[].default_org` 的上下文规则。
- 不迁移或修改用户主目录下已有配置文件内容。
- 不在本次变更中新增环境 profile 选择语法或改造配置文件结构。

## Decisions

1. 当前目录 local override 优先于用户主目录配置。

   当 `YDF_BROWSER_CONFIG` 未设置且未传 `--config`，如果 `Path.cwd()/config/env.local.yaml` 存在，`default_config_path()` 返回 `Path.cwd()/config/env.yaml`。理由是 `env.local.yaml` 通常承载真实账号和环境地址，存在该文件可以明确表达“本目录有意覆盖运行配置”。相比总是优先当前目录 `config/env.yaml`，这个条件不会让只有示例配置的源码目录意外绕过安装版的 `~/.ydf-browser` 配置。

   备选方案是要求用户始终传 `--config config/env.yaml`。这能临时规避问题，但没有修复默认运行与文档引导之间的冲突，仍容易在真实验证时误连 tv5。

2. 保留用户主目录与 release 配置兜底顺序。

   如果当前目录不存在 `config/env.local.yaml`，默认发现仍按用户主目录配置、release current 配置、当前目录配置、包内配置的顺序兜底。这样安装版命令在任意普通目录运行时保持现有行为。

3. `ConfigLoader` 提供可诊断的本地 override 信息。

   现有 `doctor` 只展示主配置路径和最终 `base_url`，无法看出哪个 `env.local.yaml` 被合并。实现阶段应让 loader 暴露 `local_config_path` 和 local 文件是否存在，并让 `doctor` 输出这些字段。该信息只用于诊断，不改变配置数据模型对业务运行的传递方式。

4. 运行期验证关注配置流，不在 `open_menu` 再做环境修正。

   `YondifGateway`、`CasAuthenticator` 和 `PlaywrightRuntime` 都接收同一个 `EnvironmentConfig`。修复后只要 loader 产出的 `env.base_url` 是 t9i，API 登录、租户/组织上下文、service tree、matchingTemplate 和浏览器菜单打开都会自然使用 t9i。避免在 runtime 层引入额外覆盖逻辑，防止 API 与浏览器环境分裂。

## Risks / Trade-offs

- [Risk] 当前目录存在 `config/env.local.yaml` 但 `config/env.yaml` 缺失时会暴露缺失主配置错误。-> Mitigation: 保持 `ConfigLoader` 对主配置 required 的现有行为，并在错误信息中显示解析出的主配置路径。
- [Risk] 某些用户可能无意中在工作目录留下旧的 `config/env.local.yaml`。-> Mitigation: `doctor` 明确输出主配置路径、本地 override 路径和最终 `base_url`，运行前可快速确认。
- [Risk] 修改默认配置优先级会影响已有测试断言。-> Mitigation: 更新单测表达新规则，并保留“无 cwd local 时仍使用用户主目录配置”的回归。
- [Risk] 真实 t9i 用例可能因业务数据或账号状态失败。-> Mitigation: 验证重点先看 `doctor` 与运行事件/报告中的 base URL 是否为 t9i；业务后续步骤失败不应掩盖环境选择验证。
