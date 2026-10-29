## ADDED Requirements

### Requirement: 合并配置后尊重显式默认用户别名
ydf-browser MUST 尊重合并后环境配置中显式配置的 `users.默认用户` 别名，不论该别名来自 `env.yaml` 还是同目录 `env.local.yaml`。

#### Scenario: env yaml 中的默认用户别名不被覆盖
- **WHEN** 选中的 `env.yaml` 同时包含环境级 `username/password` 和凭据不同的 `users.默认用户`
- **AND** 同目录 `env.local.yaml` 不存在
- **THEN** `case.user: 默认用户` SHALL 解析为 `users.默认用户` 中配置的凭据
- **AND** 配置加载 SHALL NOT 使用环境级 `username/password` 替换该别名

#### Scenario: local 默认用户别名覆盖 base 默认用户别名
- **WHEN** 选中的 `env.yaml` 包含 `users.默认用户`
- **AND** 同目录 `env.local.yaml` 也包含 `users.默认用户`
- **THEN** `case.user: 默认用户` SHALL 解析为合并后来自 `env.local.yaml` 的别名凭据

### Requirement: 仅在缺失时合成默认用户别名
ydf-browser MUST 仅在合并后的环境配置没有显式定义 `users.默认用户` 时，才使用合并后的环境级 `username/password` 合成 `users.默认用户`。

#### Scenario: 缺失默认用户别名时自动合成
- **WHEN** 合并后的环境配置包含环境级 `username/password`
- **AND** 合并后的环境配置不包含 `users.默认用户`
- **THEN** 配置加载 SHALL 使用合并后的环境级 `username/password` 增加 `users.默认用户`

#### Scenario: 空用户别名继续继承环境凭据
- **WHEN** 合并后的环境配置包含 `审核岗: {}` 这类空用户别名
- **THEN** 该空别名 SHALL 解析为合并后的环境级 `username/password`
- **AND** 该继承行为 SHALL NOT 要求别名必须定义在 `env.local.yaml` 中

#### Scenario: 示例默认用户可以跟随 local 顶层凭据
- **WHEN** 选中的 `env.yaml` 包含安装器示例 `users.默认用户` 占位凭据
- **AND** 同目录 `env.local.yaml` 只覆盖环境级 `username/password`
- **THEN** 为兼容生成的示例配置，`case.user: 默认用户` MAY 解析为合并后的环境级凭据
- **AND** 该兼容行为 SHALL NOT 覆盖用户在 `env.yaml` 中显式写出的非占位 `users.默认用户` 凭据
