## Why

安装版 README 引导用户只编辑 `~/.ydf-browser/config/env.yaml`，并在其中配置 `users.默认用户` 供 DSL 的 `case.user: 默认用户` 使用。真实反馈显示，当同样内容只存在于 `env.yaml` 时，`默认用户` 会被加载器改写为环境级 `username/password`，导致登录失败；把同样内容复制为同目录 `env.local.yaml` 后，`默认用户` 才按 `users.默认用户` 生效并能越过登录。

这个行为来自配置加载层的隐式规则，不是用户 YAML 内容差异。它让文档承诺和实际运行不一致，也让 `env.local.yaml` 承担了未说明的特殊语义。

## What Changes

- 调整 `默认用户` 别名解析规则：最终合并配置中已经显式定义 `users.默认用户` 时，运行必须尊重该别名配置。
- 仅在最终合并配置没有 `users.默认用户` 时，才自动合成一个跟随环境级 `username/password` 的 `默认用户` 别名。
- 保留空用户别名继承环境级账号的能力，例如 `审核岗: {}` 继续继承当前合并后的 `username/password`。
- 补充诊断或文档说明，让用户能理解 `env.yaml` 与同目录 `env.local.yaml` 的合并关系，以及 `默认用户` 的有效来源。
- 不改变默认配置文件发现顺序，不改变 `base_url` 合并和运行期传递规则。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `environment-config-resolution`: 增加环境配置中用户别名，尤其是 `默认用户`，在 `env.yaml` 与 `env.local.yaml` 合并后的解析要求。

## Impact

- 影响 `ydf_browser/config.py` 中 `ConfigLoader` 的用户别名解析逻辑。
- 影响 `tests/test_config.py` 中关于 `默认用户`、local override 和空别名继承的测试。
- 影响 README 或发布文档中配置说明，特别是 `~/.ydf-browser/config/env.yaml` 与 `env.local.yaml` 的关系。
- 真实运行验证应覆盖用户反馈路径：在安装版命令下只配置 `~/.ydf-browser/config/env.yaml`，执行包含 `case.user: 默认用户` 的 DSL 时应使用 `users.默认用户` 指定账号。
