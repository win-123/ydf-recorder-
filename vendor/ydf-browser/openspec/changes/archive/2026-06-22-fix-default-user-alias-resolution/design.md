## Context

`ConfigLoader` 当前先读取主配置 `env.yaml`，再读取同目录 `env.local.yaml` 并做深度合并。用户别名解析时，`_parse_users()` 会让空别名继承合并后的环境级 `username/password`，随后加载器有一段额外逻辑：只要 local 配置没有定义 `users.默认用户`，就把最终 `users["默认用户"]` 改写为环境级账号。

真实反馈路径中，安装版用户按 README 只编辑 `~/.ydf-browser/config/env.yaml`，文件内同时有环境级账号和 `users.默认用户`，且两者不是同一账号。由于没有同目录 `env.local.yaml`，`case.user: 默认用户` 被解析成环境级账号并在登录阶段失败。把完全相同的内容复制为 `env.local.yaml` 后，local 显式定义了 `默认用户`，加载器才保留 `users.默认用户`，真实用例能越过登录并执行到后续业务步骤。

这说明当前行为不是配置发现或 `base_url` 问题，而是 `默认用户` 别名在不同来源文件中的优先级不一致。

## Goals / Non-Goals

**Goals:**

- 尊重最终合并配置中显式写出的 `users.默认用户`，无论它来自 `env.yaml` 还是 `env.local.yaml`。
- 保留没有显式配置 `users.默认用户` 时自动生成默认别名的能力，降低最小配置成本。
- 保留空用户别名继承环境级账号的语义，例如 `审核岗: {}`。
- 用单测覆盖用户反馈的最小复现路径，并用真实安装版命令验证 `case.user: 默认用户` 会使用 `users.默认用户`。
- 更新 README 或发布文档，说明 `env.yaml` 与同目录 `env.local.yaml` 的合并关系，以及 `默认用户` 的有效来源。

**Non-Goals:**

- 不改变 `default_config_path()` 的配置文件发现顺序。
- 不改变 `env.local.yaml` 对普通字段、`base_url`、`variables`、`endpoints` 的覆盖规则。
- 不改变 DSL 中 `case.user` 的语法。
- 不处理用户反馈 DSL 最后一步 `table.assert_row_values` 需要 `target.table` 的独立问题。

## Decisions

1. 以“最终合并配置是否显式定义 `users.默认用户`”作为是否自动合成默认别名的判断依据。

   当前判断只看 local 配置是否定义 `默认用户`，忽略了 base 配置中已经显式定义的同名别名。修复后应先完成 `env.yaml + env.local.yaml` 深度合并，再判断合并后的 `users` 是否包含 `默认用户`。如果包含，就让 `_parse_users()` 的结果自然生效；如果不包含，再合成跟随环境级 `username/password` 的 `默认用户`。

   备选方案是继续保持当前实现，只在 README 中说明 `默认用户` 必须写进 `env.local.yaml`。这个方案不符合安装版配置入口，也会让 `env.yaml` 中的显式用户别名变成陷阱，因此不采用。

2. 保留空别名继承环境级账号。

   `_parse_users()` 目前对 `审核岗: {}` 这类空对象使用 `default_username/default_password` 补齐。这是已有配置能力，适合表达多个岗位暂时共用当前账号。修复不应改变该语义。

3. 兼容“示例默认用户跟随 local 顶层账号”的原始意图，但收窄触发条件。

   现有测试期望：`env.yaml` 里 `users.默认用户` 是安装器示例占位值，`env.local.yaml` 只覆盖顶层 `username/password` 时，`默认用户` 跟随 local 顶层账号。这类场景的合理边界是“没有真实显式别名，或显式别名仍是示例占位值”。实现时可以通过更精确的规则处理示例占位值，但不能覆盖用户在 `env.yaml` 中写出的真实 `users.默认用户`。

4. 用 `doctor` 和真实 run 把差异暴露出来。

   `doctor` 已能展示 `path/local_path/local_exists/base_url/users`，但不能展示别名解析到哪个账号。为避免泄露敏感信息，不要求 doctor 输出账号明文。真实验证侧重确认同一 DSL 在只配置 `env.yaml` 时不再因错误账号停在登录阶段；若后续业务步骤失败，应和本次配置修复分开判断。

## Risks / Trade-offs

- [Risk] 旧用户依赖“`env.local.yaml` 只写顶层账号即可覆盖示例 `默认用户`”的行为。-> Mitigation: 保留示例占位值跟随顶层账号，或在 release notes 中说明如果需要同一账号，推荐写 `默认用户: {}`。
- [Risk] 判断“示例占位值”过于硬编码。-> Mitigation: 优先测试当前安装器生成的 `your-username/your-password` 示例；其它情况尊重显式别名，避免误改真实账号。
- [Risk] README 继续只展示 `users.默认用户`，用户不理解环境级账号的用途。-> Mitigation: 文档说明环境级 `username/password` 是默认继承来源，显式用户别名优先，空别名继承环境级账号。
- [Risk] 真实用例后续业务步骤失败会干扰验收。-> Mitigation: 验证重点记录登录阶段是否越过，以及报告是否进入 `open_menu` 或后续步骤；业务断言失败单独处理。
