# environment-config-resolution Specification

## Purpose
定义 ydf-browser 在真实运行和诊断中如何发现环境配置、合并本地 override，并确保最终 `base_url` 贯穿 API 调用与浏览器菜单打开。
## Requirements
### Requirement: Default config discovery honors cwd local override
ydf-browser MUST use the current working directory configuration when no explicit config is provided and `config/env.local.yaml` exists in the current working directory.

#### Scenario: cwd local override beats user home config
- **WHEN** `YDF_BROWSER_CONFIG` is unset, no CLI `--config` is provided, `~/.ydf-browser/config/env.local.yaml` contains `base_url: https://tv5-ydf.yonyougov.top`, and the current working directory contains `config/env.local.yaml` with `base_url: https://t9i-ydf.yonyougov.top`
- **THEN** config loading SHALL use the current working directory `config/env.yaml` as the main config and the current working directory `config/env.local.yaml` as the local override
- **AND** the resulting environment `base_url` SHALL be `https://t9i-ydf.yonyougov.top`

#### Scenario: explicit config remains highest priority
- **WHEN** `YDF_BROWSER_CONFIG` or CLI `--config` points to a specific config file
- **THEN** config loading SHALL use that explicit config file and its sibling `env.local.yaml`
- **AND** current working directory local override discovery SHALL NOT replace the explicit config path

#### Scenario: user home config remains fallback without cwd local override
- **WHEN** `YDF_BROWSER_CONFIG` is unset, no CLI `--config` is provided, the user home config exists, and the current working directory does not contain `config/env.local.yaml`
- **THEN** config loading SHALL keep using the user home config according to the existing fallback behavior

### Requirement: Doctor reports effective config sources
ydf-browser MUST make the effective config source visible in diagnostics.

#### Scenario: doctor shows main and local config paths
- **WHEN** the user runs `ydf-browser doctor --env ydf`
- **THEN** the config check result SHALL include the selected main config path
- **AND** it SHALL include the sibling local config path and whether that local file exists
- **AND** it SHALL include the final merged `base_url`

### Requirement: Runtime components receive the merged base URL
ydf-browser MUST pass the merged environment `base_url` from config loading into all real-run components that open YonDiF pages or call YonDiF APIs.

#### Scenario: open_menu uses cwd local base URL
- **WHEN** the current working directory local override resolves `ydf.base_url` to `https://t9i-ydf.yonyougov.top` and a real run executes `open_menu`
- **THEN** API login, tenant context, menu gateway calls, template matching, and browser menu navigation SHALL use `https://t9i-ydf.yonyougov.top`
- **AND** browser navigation SHALL NOT fall back to `https://tv5-ydf.yonyougov.top` unless that is the resolved merged `base_url`

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

### Requirement: 业务年度端点使用合并后的环境 base URL
ydf-browser MUST 在调用业务年度切换端点时使用已解析合并后的环境配置。

#### Scenario: 业务年度切换使用配置后的 base URL
- **WHEN** 配置加载将 `ydf.base_url` 解析为 `https://t9i-ydf.yonyougov.top`，且真实运行 suite 声明 `fiscal_year: "2027"`
- **THEN** 业务年度切换请求 SHALL 发送到 `https://t9i-ydf.yonyougov.top/yondif-ams-be/context/switch/fiscal/year?fiscalYear=2027`
- **AND** 除非其它 URL 是已解析合并后的 `base_url`，否则该请求 SHALL NOT 使用其它 base URL

#### Scenario: 环境配置可以覆盖业务年度端点
- **WHEN** 已选环境配置覆盖 `endpoints.switch_fiscal_year`
- **THEN** ydf-browser SHALL 使用覆盖后的端点路径和已解析合并后的 `base_url`
- **AND** 租户上下文、默认组织、菜单网关、模板匹配和浏览器导航 SHALL 继续使用同一个已解析环境

### Requirement: 校验指令解析选中环境的变量
ydf-browser MUST 在 `validate` 加载 DSL 前读取选中环境的合并配置变量，并与其它外部变量来源使用和 `run` 相同的覆盖顺序。

#### Scenario: 当前目录本地变量参与校验
- **WHEN** 当前工作目录的 `config/env.local.yaml` 在 `environments.ydf.variables` 中声明 DSL 引用的变量，用户运行 `ydf-browser validate --dsl <path>`
- **THEN** `validate` SHALL 使用合并后的环境变量解析 DSL
- **AND** 校验 SHALL NOT 将该变量报告为未定义

#### Scenario: 校验指令尊重显式环境配置
- **WHEN** 用户运行 `ydf-browser validate --dsl <path> --env <name> --config <path>`
- **THEN** `validate` SHALL 从指定配置文件及其同目录 `env.local.yaml` 读取指定环境的变量

#### Scenario: 命令行输入覆盖环境变量
- **WHEN** 环境配置、`--vars-file` 和 `--var` 声明同一个变量
- **THEN** `validate` SHALL 按环境配置、`--vars-file`、`--var` 的顺序深度合并变量
- **AND** 后一个来源 SHALL 覆盖前一个来源的同名值

### Requirement: 环境配置提供独立 BPR 下载凭据
ydf-browser SHALL 从所选环境的可选 `bpr.username` 和 `bpr.password` 读取 BPR 报告下载凭据，并将其与业务用户凭据完全分离。

环境配置 MUST NOT 提供 BPR 报告地址；登录 origin 和下载页面地址只能来自经过安全校验的 `bpr.stop` 返回 `report_url`。

#### Scenario: BPR 凭据完整配置
- **WHEN** 合并后的所选环境同时包含非空 `bpr.username` 和 `bpr.password`
- **THEN** 配置加载 MUST 接受这组 BPR 凭据
- **AND** BPR 报告下载 MUST 使用该组凭据
- **AND** 业务登录 MUST 继续使用既有业务用户解析结果

#### Scenario: BPR 凭据均未配置
- **WHEN** 合并后的所选环境没有非空 `bpr.username` 和 `bpr.password`
- **THEN** 配置加载 MUST 允许业务运行继续
- **AND** 系统 MUST 将 BPR 下载能力视为未配置

#### Scenario: BPR 凭据只配置一项
- **WHEN** 环境的 `bpr.username` 和 `bpr.password` 只有一项非空
- **THEN** 配置加载 MUST 在启动浏览器前失败
- **AND** 错误消息 MUST 说明 BPR 用户名和密码必须成对配置

#### Scenario: BPR 凭据不回退到业务用户
- **WHEN** 环境未配置完整 BPR 凭据但配置了业务用户凭据
- **THEN** 系统 MUST NOT 使用环境级业务凭据或 `users` 别名凭据下载 BPR 报告

#### Scenario: BPR 秘密不进入运行产物
- **WHEN** 配置加载或 BPR 后处理使用 BPR 凭据
- **THEN** BPR 用户名和密码 MUST NOT 进入 DSL、报告、性能工作簿、事件、错误文本或文件名
- **AND** 提交到版本控制的配置示例 MUST 只包含占位值
