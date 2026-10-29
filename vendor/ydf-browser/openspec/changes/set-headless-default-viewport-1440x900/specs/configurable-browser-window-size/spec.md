## MODIFIED Requirements

### Requirement: 未指定时保留默认窗口行为

当用户未提供 `--window-size` 时，系统 MUST 不显式设置 headed Chromium `--window-size`，且 headed context MUST 使用 `no_viewport=True` 让页面 viewport 跟随宿主窗口；headless context MUST 使用固定 `1440×900` viewport，且 MUST 不设置 `no_viewport` 或无效的 Chromium 外层窗口尺寸参数。

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

- **WHEN** 用户运行持久化或非持久化 headless 浏览器且未提供 `--window-size`
- **THEN** browser context viewport MUST 为 `1440×900`
- **AND** 系统 MUST 不设置 `no_viewport`
- **AND** 系统 MUST 不向 Chromium 启动参数加入 `--window-size`
