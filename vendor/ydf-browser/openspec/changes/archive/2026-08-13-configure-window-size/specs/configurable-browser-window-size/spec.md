## Purpose

为不同宿主窗口和持久化 profile 提供可选择的浏览器尺寸控制，同时避免无参数启动时覆盖操作系统或浏览器自身的默认窗口行为。

## ADDED Requirements

### Requirement: 显式窗口尺寸参数

`run` 命令 MUST 支持可选的 `--window-size WIDTHxHEIGHT` 参数，其中 `WIDTH` 和 `HEIGHT` MUST 是正整数。

#### Scenario: 接受合法窗口尺寸

- **WHEN** 用户运行 `run --window-size 1440x900`
- **THEN** 系统 MUST 接受该参数
- **AND** MUST 将宽度解析为 `1440`、高度解析为 `900`

#### Scenario: 拒绝非法窗口尺寸

- **WHEN** 用户提供缺少维度、非正整数或非 `WIDTHxHEIGHT` 格式的 `--window-size` 值
- **THEN** 系统 MUST 在启动浏览器前失败
- **AND** 错误信息 MUST 指明窗口尺寸格式无效

### Requirement: 未指定时保留默认窗口行为

当用户未提供 `--window-size` 时，系统 MUST 不显式设置 Chromium `--window-size`，且 headed context MUST 使用 `no_viewport=True` 让页面 viewport 跟随宿主窗口；headless context MUST 不显式覆盖 viewport 或设置 `no_viewport`。

#### Scenario: 非持久化 headed 浏览器未指定尺寸

- **WHEN** 用户运行非持久化 headed 浏览器且未提供 `--window-size`
- **THEN** 系统 MUST 不向 Chromium 启动参数加入 `--window-size`
- **AND** MUST 向 browser context 设置 `no_viewport=True`
- **AND** 页面 viewport MUST 随宿主窗口调整

#### Scenario: 持久化 headed 浏览器未指定尺寸

- **WHEN** 用户运行持久化 headed 浏览器且未提供 `--window-size`
- **THEN** 系统 MUST 不向持久化浏览器启动参数加入 `--window-size`
- **AND** MUST 向持久化 browser context 设置 `no_viewport=True`
- **AND** 页面 viewport MUST 随宿主窗口调整

#### Scenario: Headless 浏览器未指定尺寸

- **WHEN** 用户运行 headless 浏览器且未提供 `--window-size`
- **THEN** 系统 MUST 不显式设置 viewport
- **AND** MUST 不设置 `no_viewport`

### Requirement: 显式尺寸应用于浏览器启动

当用户提供合法的 `--window-size` 时，系统 MUST 在 headed 的持久化和非持久化启动路径将该尺寸传给 Chromium 外层窗口作为启动尺寸，并 MUST 使用 `no_viewport=True` 让页面 viewport 在运行中跟随宿主窗口；headless 模式 MUST 将该尺寸用于页面 viewport。

#### Scenario: 非持久化 headed 浏览器使用显式尺寸

- **WHEN** 用户运行非持久化 headed 浏览器并提供 `--window-size 1600x1000`
- **THEN** Chromium 启动参数 MUST 包含 `--window-size=1600,1000`
- **AND** browser context MUST 设置 `no_viewport=True`
- **AND** 启动后手工调整窗口时页面 viewport MUST 跟随窗口变化

#### Scenario: 持久化 headed 浏览器使用显式尺寸

- **WHEN** 用户运行持久化 headed 浏览器并提供 `--window-size 1600x1000`
- **THEN** 持久化浏览器启动参数 MUST 包含 `--window-size=1600,1000`
- **AND** 持久化 browser context MUST 设置 `no_viewport=True`
- **AND** 启动后手工调整窗口时页面 viewport MUST 跟随窗口变化

#### Scenario: Headless 浏览器使用显式 viewport

- **WHEN** 用户运行 headless 浏览器并提供 `--window-size 1600x1000`
- **THEN** 页面 viewport MUST 为 `1600×1000`
- **AND** 系统 MUST NOT 因不存在外层窗口而要求 Chromium `--window-size` 参数

### Requirement: 既有运行语义保持不变

窗口尺寸配置 MUST 不改变登录、profile 选择、请求转发、DSL 执行、报告生成和退出码语义。

#### Scenario: 尺寸参数不改变运行模式

- **WHEN** 用户在原有 `run` 命令上增加合法的 `--window-size`
- **THEN** 系统 MUST 继续使用原有登录和 profile 流程
- **AND** MUST 继续执行原有 DSL 或手工浏览器会话流程
